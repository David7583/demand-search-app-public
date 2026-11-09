"""Immutable private demand versions; AI results cannot confirm or publish themselves."""

import copy
import hashlib
import json
import time
from uuid import uuid4

from pydantic import ValidationError

from . import ncp_adapter
from .ai_demand import prepare_context
from .collaboration import validate_helpfulness
from .demand_models import DemandData, Edits
from .errors import AppError
from .history_service import HistoryService, checked_id, checked_text, now
from .storage import LOCAL_OWNER, connect

MAX_VERSIONS = 100
LEASE_SECONDS = 120


def encode(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
    )


def version_view(row):
    if row is None:
        return None
    value = dict(row)
    value["data"] = json.loads(value.pop("data_json"))
    value["data"].setdefault("items", [])  # Read compatibility only; never rewrite stored JSON.
    value["user_confirmed"] = value["status"] == "confirmed"
    return value


def validate_data(value, *, ai=False):
    try:
        data = DemandData.model_validate(value, strict=True).model_dump()
        checked_text(data["desired_outcome"], limit=1000)
        if ai and (data["solution_confirmed"] or data["solution_selection"] is not None):
            raise ValueError("AI cannot adopt solutions")
        for field in ("unknown", "clarification_questions"):
            for text in data[field]:
                checked_text(text, limit=500)
        for field in ("required", "preferred"):
            for fact in data[field]:
                checked_text(fact["text"], limit=500)
                if ai and (fact["confirmed"] or fact["source"] == "user_confirmed"):
                    raise ValueError("AI cannot confirm")
        budget = data["budget_ceiling"]
        if ai and budget and (budget["confirmed"] or budget["source"] == "user_confirmed"):
            raise ValueError("AI cannot confirm")
        identities = set()
        for item in data["items"]:
            identity = checked_id(item["item_id"])
            if identity in identities:
                raise ValueError("Duplicate item ID")
            identities.add(identity)
            checked_text(item["name"], limit=120)
            if item["unit"] is not None:
                checked_text(item["unit"], limit=32)
            for text in item["unknown"]:
                checked_text(text, limit=500)
            if ai and (item["confirmed"] or item["source"] == "user_confirmed"):
                raise ValueError("AI cannot confirm items")
            for field in ("required", "preferred"):
                for fact in item[field]:
                    checked_text(fact["text"], limit=500)
                    if ai and (fact["confirmed"] or fact["source"] == "user_confirmed"):
                        raise ValueError("AI cannot confirm item conditions")
            budget = item["budget_ceiling"]
            if ai and budget and (budget["confirmed"] or budget["source"] == "user_confirmed"):
                raise ValueError("AI cannot confirm item budgets")
        encode(data)
        return data
    except (ValueError, TypeError, ValidationError, UnicodeError, AppError):
        raise AppError("DEMAND_STRUCTURE_INVALID", "需求结构无效，未修改已有版本。", 422) from None


def bind_ai_items(parsed, context):
    """Only the server creates IDs; omitted entries retain prior provenance unchanged."""
    previous = context.get("current_draft") or context.get("confirmed_demand") or {}
    old_items = previous.get("items", [])
    known = {item["item_id"]: item for item in old_items}
    supplied = parsed.get("items", [])
    if not isinstance(supplied, list):
        raise AppError("DEMAND_STRUCTURE_INVALID", "Invalid shopping list.", 422)
    bound, seen = [], set()
    for value in supplied:
        if not isinstance(value, dict):
            raise AppError("DEMAND_STRUCTURE_INVALID", "Invalid shopping item.", 422)
        item = copy.deepcopy(value)
        identity = item.get("item_id")
        if identity is None:
            identity = str(uuid4())
        elif identity not in known:
            raise AppError("ITEM_ID_UNKNOWN", "Item ID does not belong to this demand.", 422)
        if identity in seen:
            raise AppError("ITEM_ID_DUPLICATE", "Repeated item ID; no version saved.", 422)
        seen.add(identity)
        item["item_id"] = identity
        bound.append(item)
    # Validate untrusted AI entries BEFORE merging previously confirmed facts.
    data = validate_data({**parsed, "items": bound}, ai=True)
    data["items"].extend(copy.deepcopy(item) for item in old_items if item["item_id"] not in seen)
    if len(data["items"]) > 30:
        raise AppError(
            "ITEM_LIMIT_REACHED", "At most 30 list entries; split into another conversation.", 422
        )
    return validate_data(data)


def confirmed_facts(original, values):
    facts = []
    for text in values:
        checked_text(text, limit=500)
        old = next((v for v in original if v["text"] == text), None)
        fact = dict(old) if old else {"text": text, "source": "user_confirmed", "evidence": text}
        fact["confirmed"] = fact["source"] != "unknown"
        facts.append(fact)
    return facts


def confirmed_budget(original, value):
    if value is None:
        return None
    if original and all(original[key] == value[key] for key in ("amount", "currency")):
        return {**original, "confirmed": original["source"] != "unknown"}
    return {
        **value,
        "source": "user_confirmed",
        "evidence": "User edited the budget in the confirmation form",
        "confirmed": True,
    }


def edited_items(original, edits):
    if edits is None:
        return copy.deepcopy(original)  # Old clients cannot certify unseen new fields.
    known = {item["item_id"]: item for item in original}
    edited, seen = [], set()
    for value in edits:
        identity = value["item_id"]
        if identity not in known:
            raise AppError("ITEM_ID_UNKNOWN", "Only this demand's item IDs can be edited.", 422)
        if identity in seen:
            raise AppError("ITEM_ID_DUPLICATE", "Repeated item ID; no version saved.", 422)
        seen.add(identity)
        old = known[identity]
        item = {**copy.deepcopy(old), **value}
        if any(value[field] != old[field] for field in ("name", "quantity", "unit", "status")):
            item.update(
                source="user_confirmed", evidence="User edited the item in the confirmation form"
            )
        item["confirmed"] = item["source"] != "unknown"
        for field in ("required", "preferred"):
            item[field] = confirmed_facts(old[field], value[field])
        item["budget_ceiling"] = confirmed_budget(old["budget_ceiling"], value["budget_ceiling"])
        if item["budget_ceiling"] and old["budget_basis"] != value["budget_basis"]:
            item["budget_ceiling"].update(
                source="user_confirmed",
                confirmed=True,
                evidence="User edited the budget basis in the confirmation form",
            )
        edited.append(item)
    # Deletion must be represented explicitly as status=removed, not by omission.
    edited.extend(copy.deepcopy(item) for item in original if item["item_id"] not in seen)
    return edited


class DemandService:
    def __init__(self, settings, models):
        self.settings = settings
        self.models = models
        self.history = HistoryService(settings)

    def _owned(self, db, conversation_id):
        return self.history._conversation(db, conversation_id)

    def _demand(self, db, conversation_id):
        return db.execute(
            "SELECT * FROM demands WHERE conversation_id=? AND owner_id=?",
            (conversation_id, LOCAL_OWNER),
        ).fetchone()

    def _detail(self, db, conversation_id):
        self._owned(db, conversation_id)
        row = self._demand(db, conversation_id)
        if row is None:
            return {
                "demand": None,
                "versions": [],
                "current_version": None,
                "confirmed_version": None,
            }
        versions = [
            version_view(v)
            for v in db.execute(
                "SELECT * FROM demand_versions WHERE demand_id=? ORDER BY number DESC", (row["id"],)
            )
        ]
        by_id = {v["id"]: v for v in versions}
        demand = {
            k: row[k]
            for k in (
                "id",
                "intent_id",
                "status",
                "current_version_id",
                "confirmed_version_id",
                "ncp_revision",
                "created_at",
                "updated_at",
            )
        }
        return {
            "demand": demand,
            "versions": versions,
            "current_version": by_id.get(row["current_version_id"]),
            "confirmed_version": by_id.get(row["confirmed_version_id"]),
        }

    def get(self, conversation_id):
        conversation_id = checked_id(conversation_id)
        with connect(self.settings) as db:
            return self._detail(db, conversation_id)

    def _expected(self, row, expected):
        if row and row["status"] == "withdrawn":
            raise AppError("DEMAND_WITHDRAWN", "此需求已撤回；请新建会话表达新的需求。", 409)
        if expected is not None:
            expected = checked_id(expected)
        if (row["current_version_id"] if row else None) != expected:
            raise AppError("DEMAND_VERSION_CONFLICT", "需求版本已变化，请刷新后重新操作。", 409)

    def _message(self, db, conversation_id, identity):
        message = db.execute(
            "SELECT id,content,sequence,metadata_json FROM conversation_messages WHERE id=? "
            "AND conversation_id=? AND owner_id=? AND role='user'",
            (checked_id(identity), conversation_id, LOCAL_OWNER),
        ).fetchone()
        if message is None:
            raise AppError("MESSAGE_NOT_FOUND", "本会话中不存在该用户原文。", 404)
        return message

    def _latest_sequence(self, db, conversation_id):
        return db.execute(
            "SELECT coalesce(max(sequence),0) FROM conversation_messages "
            "WHERE conversation_id=? AND role='user'",
            (conversation_id,),
        ).fetchone()[0]

    def _claim(self, db, conversation_id, operation, body):
        identity = checked_id(body["request_id"])
        try:
            fingerprint = hashlib.sha256(encode(body).encode()).hexdigest()
        except (ValueError, TypeError, UnicodeError):
            raise AppError(
                "DEMAND_REQUEST_INVALID", "Request must contain finite JSON values.", 422
            ) from None
        old = db.execute("SELECT * FROM demand_requests WHERE id=?", (identity,)).fetchone()
        if old:
            if (
                old["conversation_id"] != conversation_id
                or old["operation"] != operation
                or old["payload_hash"] != fingerprint
            ):
                raise AppError("REQUEST_ID_CONFLICT", "请求ID已有不同内容或属于其他会话。", 409)
            if old["state"] == "completed":
                return None, old["version_id"]
            if old["state"] == "pending" and old["lease_until"] > time.time():
                raise AppError("REQUEST_IN_PROGRESS", "此请求仍在处理，请稍后重试相同请求。", 409)
        count = db.execute(
            "SELECT count(*) FROM demand_requests WHERE conversation_id=?", (conversation_id,)
        ).fetchone()[0]
        if not old and count >= 1000:
            raise AppError("DEMAND_LIMIT_REACHED", "此会话请求过多，请导出后新建会话。", 409)
        token = str(uuid4())
        db.execute(
            "INSERT INTO demand_requests(id,conversation_id,operation,payload_hash,state,"
            "claim_token,lease_until,updated_at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET state='pending',claim_token=excluded.claim_token,"
            "lease_until=excluded.lease_until,updated_at=excluded.updated_at",
            (
                identity,
                conversation_id,
                operation,
                fingerprint,
                "pending",
                token,
                time.time() + LEASE_SECONDS,
                now(),
            ),
        )
        return token, None

    def _finish(self, db, request_id, token, version_id):
        changed = db.execute(
            "UPDATE demand_requests SET state='completed',version_id=?,updated_at=? "
            "WHERE id=? AND claim_token=? AND state='pending'",
            (version_id, now(), request_id, token),
        )
        if changed.rowcount != 1:
            raise AppError("REQUEST_REPLACED", "请求已被恢复任务替代，请刷新后检查版本。", 409)

    def _response(self, db, conversation_id, version_id, duplicate=False):
        return {
            **self._detail(db, conversation_id),
            "result_version_id": version_id,
            "duplicate": duplicate,
        }

    def _new_version(
        self, db, demand, message, data, status, *, model=None, provider=None, prompt_version=None
    ):
        number = db.execute(
            "SELECT coalesce(max(number),0)+1 FROM demand_versions WHERE demand_id=?",
            (demand["id"],),
        ).fetchone()[0]
        if number > MAX_VERSIONS:
            raise AppError("DEMAND_LIMIT_REACHED", "本需求版本已达上限，请导出后新建会话。", 409)
        identity = str(uuid4())
        db.execute(
            "INSERT INTO demand_versions(id,demand_id,number,parent_version_id,source_message_id,"
            "original_text,data_json,status,model,provider,prompt_version,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                identity,
                demand["id"],
                number,
                demand["current_version_id"],
                message["id"],
                message["content"],
                encode(data),
                status,
                model,
                provider,
                prompt_version,
                now(),
            ),
        )
        db.execute(
            "UPDATE demands SET current_version_id=?,updated_at=? WHERE id=?",
            (identity, now(), demand["id"]),
        )
        return identity

    def _context(self, db, row, conversation_id, message):
        confirmed = None
        if row and row["confirmed_version_id"]:
            record = db.execute(
                "SELECT data_json FROM demand_versions WHERE id=?", (row["confirmed_version_id"],)
            ).fetchone()
            confirmed = json.loads(record["data_json"])
        recent = db.execute(
            "SELECT id,content,sequence FROM conversation_messages "
            "WHERE conversation_id=? AND owner_id=? AND role='user' AND sequence<? "
            "ORDER BY sequence DESC LIMIT 6",
            (conversation_id, LOCAL_OWNER, message["sequence"]),
        ).fetchall()
        selected, remaining = [], 6000
        for old in recent:
            if not remaining:
                break
            item = dict(old)
            if len(item["content"]) > remaining:
                item["content"] = item["content"][:remaining]
                item["truncated"] = True
            remaining -= len(item["content"])
            selected.append(item)
        current_draft = None
        if row and row["current_version_id"]:
            current = db.execute(
                "SELECT data_json,status FROM demand_versions WHERE id=?",
                (row["current_version_id"],),
            ).fetchone()
            if current["status"] == "draft":
                current_draft = json.loads(current["data_json"])
        context = {
            "confirmed_demand": confirmed,
            "current_draft": current_draft,
            "recent_messages": list(reversed(selected)),
        }
        reference = json.loads(message["metadata_json"]).get("reference_version")
        if reference is not None:
            # Reload the immutable snapshot, not client-supplied labels/content. This
            # association survives refresh/retry and never alters the current pointer.
            version = self.history._referenced_version(db, conversation_id, reference["id"])
            context["referenced_version"] = {
                **{key: version[key] for key in ("id", "number", "status")},
                "data": json.loads(version["data_json"]),
            }
        return context

    def parse(
        self, conversation_id, body, *, on_delta=None, collaborative=False, cancel_check=None
    ):
        body = {**body, "request_id": checked_id(body["request_id"])}
        conversation_id = checked_id(conversation_id)
        if body.get("consent") is not True:
            raise AppError("AI_CONSENT_REQUIRED", "请明确同意发送本次原文和有限的本会话上下文。")
        with connect(self.settings) as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned(db, conversation_id)
            token, old = self._claim(
                db, conversation_id, "collaborate" if collaborative else "parse", body
            )
            if token is None:
                return self._response(db, conversation_id, old, True)
            row = self._demand(db, conversation_id)
            self._expected(row, body.get("expected_version_id"))
            message = dict(self._message(db, conversation_id, body["message_id"]))
            sequence = self._latest_sequence(db, conversation_id)
            if message["sequence"] != sequence:
                raise AppError("STALE_MESSAGE", "请解析本会话最新原文，避免覆盖较新的修改。", 409)
            context = self._context(db, row, conversation_id, message)
        try:
            # The network request never owns a database write lock.
            if cancel_check:
                cancel_check()
            # Reject the complete context before any model/network invocation.
            # Historical plans are never silently truncated to make the request fit.
            prepare_context(message["content"], context)
            options = {"on_delta": on_delta, "collaborative": True} if collaborative else {}
            result = self.models.parse_demand(
                message["content"], context, True, body.get("config_id"), **options
            )
            parsed = dict(result["parsed"])
            if (
                parsed.pop("user_confirmed", False) is not False
                or parsed.pop("original_text", message["content"]) != message["content"]
            ):
                raise AppError(
                    "DEMAND_STRUCTURE_INVALID", "AI cannot rewrite or confirm original text.", 422
                )
            data = bind_ai_items(parsed, context)
            if collaborative:
                validate_helpfulness(data)
            if cancel_check:
                cancel_check()
            with connect(self.settings) as db:
                db.execute("BEGIN IMMEDIATE")
                self._owned(db, conversation_id)
                row = self._demand(db, conversation_id)
                self._expected(row, body.get("expected_version_id"))
                current = self._message(db, conversation_id, body["message_id"])
                if (
                    current["content"] != message["content"]
                    or self._latest_sequence(db, conversation_id) != sequence
                ):
                    raise AppError(
                        "STALE_ANALYSIS", "解析期间会话出现新消息，请解析最新原文。", 409
                    )
                if row is None:
                    identity, intent_id = str(uuid4()), str(uuid4())
                    instance = db.execute(
                        "SELECT value FROM app_metadata WHERE key='instance_id'"
                    ).fetchone()[0]
                    db.execute(
                        "INSERT INTO demands(id,conversation_id,owner_id,intent_id,"
                        "sender_id,status,"
                        "created_at,updated_at) VALUES (?,?,?,?,?,'active',?,?)",
                        (
                            identity,
                            conversation_id,
                            LOCAL_OWNER,
                            intent_id,
                            "local-" + instance,
                            now(),
                            now(),
                        ),
                    )
                    row = self._demand(db, conversation_id)
                version = self._new_version(
                    db,
                    row,
                    message,
                    data,
                    "draft",
                    model=result["actual_model"],
                    provider=result["provider"],
                    prompt_version=result.get("prompt_version"),
                )
                if cancel_check:
                    cancel_check()
                self._finish(db, body["request_id"], token, version)
                return self._response(db, conversation_id, version)
        except BaseException:
            with connect(self.settings) as db:
                db.execute(
                    "UPDATE demand_requests SET state='failed',updated_at=? "
                    "WHERE id=? AND claim_token=? AND state='pending'",
                    (now(), body["request_id"], token),
                )
            raise

    def _previous(self, db, demand_id):
        return [
            json.loads(row["packet_bytes"])
            for row in db.execute(
                "SELECT packet_bytes FROM demand_packets WHERE demand_id=? ORDER BY sequence",
                (demand_id,),
            )
        ]

    def _packet(self, db, demand, packet, version_id):
        ncp_adapter.validate_packet(packet, previous=self._previous(db, demand["id"]))
        blob = ncp_adapter.serialize_packet(packet)
        sequence = db.execute(
            "SELECT coalesce(max(sequence),0)+1 FROM demand_packets WHERE demand_id=?",
            (demand["id"],),
        ).fetchone()[0]
        db.execute(
            "INSERT INTO demand_packets(id,demand_id,version_id,sequence,packet_bytes,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (packet["message_id"], demand["id"], version_id, sequence, blob, now()),
        )

    def _edited_data(self, original, edits):
        try:
            edits = Edits.model_validate(edits, strict=True).model_dump()
        except ValidationError:
            raise AppError(
                "DEMAND_EDIT_INVALID", "请检查修改字段；替代方案选项需要明确选择。", 422
            ) from None
        data = dict(original)
        for field in ("desired_outcome", "unknown", "readiness", "alternatives_acceptable"):
            data[field] = edits[field]
        for field in ("required", "preferred"):
            data[field] = confirmed_facts(original[field], edits[field])
        data["budget_ceiling"] = confirmed_budget(
            original["budget_ceiling"], edits["budget_ceiling"]
        )
        data["items"] = edited_items(original.get("items", []), edits["items"])
        data["possible_new_intent"] = False
        return validate_data(data)

    def confirm(self, conversation_id, body):
        body = {**body, "request_id": checked_id(body["request_id"])}
        conversation_id = checked_id(conversation_id)
        if body.get("confirm") is not True:
            raise AppError("CONFIRMATION_REQUIRED", "请明确确认需求卡片；这不构成购买承诺。")
        with connect(self.settings) as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned(db, conversation_id)
            token, old = self._claim(db, conversation_id, "confirm", body)
            if token is None:
                return self._response(db, conversation_id, old, True)
            row = self._demand(db, conversation_id)
            self._expected(row, body["version_id"])
            if row is None:
                raise AppError("DEMAND_NOT_FOUND", "尚无可确认的需求。", 404)
            version = db.execute(
                "SELECT * FROM demand_versions WHERE id=?", (row["current_version_id"],)
            ).fetchone()
            original = json.loads(version["data_json"])
            if original["possible_new_intent"] and body.get("continue_current_intent") is not True:
                raise AppError(
                    "INTENT_CLARIFICATION_REQUIRED", "请确认属于当前需求的修改，或新建会话。", 409
                )
            data = self._edited_data(original, body["edits"])
            selection = body.get("selected_option_id")
            confirm_solution = body.get("confirm_solution", False)
            if not isinstance(confirm_solution, bool):
                raise AppError("SOLUTION_CONFIRMATION_INVALID", "方案确认值无效。", 422)
            plan = data.get("collaboration")
            known_options = {option["option_id"] for option in (plan or {}).get("options", [])}
            if selection is not None and selection not in known_options:
                raise AppError("SOLUTION_OPTION_UNKNOWN", "请选择此版本中的方案。", 422)
            if confirm_solution and (not plan or (known_options and selection is None)):
                raise AppError("SOLUTION_SELECTION_REQUIRED", "请明确选择要采纳的方案。", 422)
            if confirm_solution and plan["needs_verification"]:
                raise AppError(
                    "SOLUTION_REQUIRES_VERIFICATION",
                    "关键条件尚待核实，不能把方案标为已采纳。",
                    409,
                )
            # This explicit action never turns assumptions/estimates into verified facts.
            data["solution_selection"] = (
                {"option_id": selection, "status": "user_selected"} if selection else None
            )
            data["solution_confirmed"] = confirm_solution
            message = self._message(db, conversation_id, version["source_message_id"])
            if self._latest_sequence(db, conversation_id) != message["sequence"]:
                raise AppError(
                    "STALE_ANALYSIS", "New messages need analysis before confirmation.", 409
                )
            new_id = self._new_version(
                db,
                row,
                message,
                data,
                "confirmed",
                model=version["model"],
                provider=version["provider"],
                prompt_version=version["prompt_version"],
            )
            revision = row["ncp_revision"] + 1
            intent = ncp_adapter.map_intent(version["original_text"], data, user_confirmed=True)
            packet = ncp_adapter.build_packet(
                "intent.publish" if revision == 1 else "intent.update",
                intent_id=row["intent_id"],
                sender_id=row["sender_id"],
                intent=intent,
                revision=revision if revision > 1 else None,
            )
            self._packet(db, row, packet, new_id)
            db.execute(
                "UPDATE demands SET confirmed_version_id=?,ncp_revision=? WHERE id=?",
                (new_id, revision, row["id"]),
            )
            self._finish(db, body["request_id"], token, new_id)
            return self._response(db, conversation_id, new_id)

    def withdraw(self, conversation_id, body):
        body = {**body, "request_id": checked_id(body["request_id"])}
        conversation_id = checked_id(conversation_id)
        if body.get("confirm") is not True:
            raise AppError("CONFIRMATION_REQUIRED", "请明确确认撤回；这不会取消任何站外订单。")
        reason = body.get("reason", "")
        if reason:
            checked_text(reason, limit=500)
        with connect(self.settings) as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned(db, conversation_id)
            token, old = self._claim(db, conversation_id, "withdraw", body)
            if token is None:
                return self._response(db, conversation_id, old, True)
            row = self._demand(db, conversation_id)
            self._expected(row, body["expected_version_id"])
            if row is None or not row["confirmed_version_id"]:
                raise AppError(
                    "DEMAND_NOT_CONFIRMED", "尚无已确认的本地意图；可删除私人会话。", 409
                )
            packet = ncp_adapter.build_packet(
                "intent.withdraw",
                intent_id=row["intent_id"],
                sender_id=row["sender_id"],
                reason=reason,
            )
            self._packet(db, row, packet, row["current_version_id"])
            db.execute(
                "UPDATE demands SET status='withdrawn',updated_at=? WHERE id=?", (now(), row["id"])
            )
            self._finish(db, body["request_id"], token, row["current_version_id"])
            return self._response(db, conversation_id, row["current_version_id"])

    def export(self, conversation_id, acknowledge_private_export):
        if acknowledge_private_export is not True:
            raise AppError(
                "PRIVATE_EXPORT_CONSENT_REQUIRED", "导出包含私人原文，请确认仅保存并自行保管。"
            )
        with connect(self.settings) as db:
            self._owned(db, conversation_id)
            demand = self._demand(db, conversation_id)
            packets = (
                []
                if demand is None
                else [
                    bytes(row["packet_bytes"]).decode("utf-8")
                    for row in db.execute(
                        "SELECT packet_bytes FROM demand_packets "
                        "WHERE demand_id=? ORDER BY sequence",
                        (demand["id"],),
                    )
                ]
            )
            ncp_adapter.validate_sequence([json.loads(packet) for packet in packets])
            return {
                "format": "demand-search.private-ncp-export/1",
                "protocol": "ODIP/0.1.3-exp.1",
                "sharing_scope": "private",
                "network_transmitted": False,
                "packets": [json.loads(packet) for packet in packets],
                "packet_utf8": packets,
                "sha256": [hashlib.sha256(packet.encode()).hexdigest() for packet in packets],
            }

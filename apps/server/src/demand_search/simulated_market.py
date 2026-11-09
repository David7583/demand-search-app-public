"""Local synthetic catalog, separate SQLite store, and conservative matching. No transport."""

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from decimal import Decimal
from functools import lru_cache

from .errors import AppError
from .history_service import HistoryService, checked_id
from .market_catalog import SEED_DATE, SEED_TIMESTAMP, SEED_VERSION, generate_catalog, stable_id
from .ncp_adapter import WIRE, validate_packet, validate_schema
from .storage import LOCAL_OWNER

DATABASE_NAME = "simulated-market.sqlite3"
BROAD_ALIASES = {
    "电脑",
    "computer",
    "ai",
    "机器人",
    "robot",
    "设备",
    "equipment",
    "硬件",
    "hardware",
    "软件",
    "software",
    "服务",
    "service",
    "家具",
    "furniture",
}
STORE_VERSION = "1"
PRIVACY = {"sharing_scope": "private", "allow_aggregate_analytics": False}
NOTICE = "本地虚构模拟市场：500家商家、1500项模拟商品/服务；不代表真实商家、库存、报价或交易。"
NOTICE_EN = (
    "Local synthetic market: 500 fictional merchants and 1,500 simulated offerings. "
    "No real merchants, inventory, quotes or transactions."
)
LIMITATION = "硬约束、配送、税费及库存均未核实；关键词相关性不代表需求符合度。"
LIMITATION_EN = (
    "Requirements, delivery, taxes and inventory are unverified; "
    "keyword relevance is not a measure of fit."
)


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def market_error():
    return AppError(
        "SIMULATED_MARKET_INTEGRITY",
        "模拟市场版本或种子完整性检查失败；数据未重置，请使用独立初始化脚本显式重建。",
        503,
    )


def validate_market_packet(packet):
    """Use the pinned schema without changing the intent adapter's supported messages."""
    validate_schema(packet)
    kind = packet["message_type"]
    simulation = packet.get("extensions", {}).get("demand_search_simulation_v1", {})
    if (
        kind not in {"capability.advertise", "proposal.submit"}
        or simulation.get("data_origin") != "synthetic"
        or simulation.get("local_only") is not True
        or simulation.get("privacy") != PRIVACY
    ):
        raise AppError("SIMULATED_PACKET_INVALID", "Invalid private simulation envelope", 422)
    if kind == "proposal.submit":
        if (
            packet.get("intent_id") != packet["payload"]["target_intent_id"]
            or not simulation.get("version_id")
            or not simulation.get("offering_id")
        ):
            raise AppError("SIMULATED_PACKET_INVALID", "Invalid simulation intent linkage", 422)


def envelope(kind, merchant_id, identity, payload, **context):
    packet = {
        "protocol": WIRE,
        "message_id": stable_id(identity),
        "message_type": kind,
        "timestamp": SEED_TIMESTAMP,
        "sender": {"participant_id": merchant_id},
        "payload": payload,
        "extensions": {
            "demand_search_simulation_v1": {
                "data_origin": "synthetic",
                "local_only": True,
                "seed_version": SEED_VERSION,
                "seed_date": SEED_DATE,
                "privacy": dict(PRIVACY),
                **context,
            }
        },
    }
    return packet


def capability(merchant):
    packet = envelope(
        "capability.advertise",
        merchant["id"],
        "capability:" + merchant["id"],
        {
            "kind": merchant["offerings"][0]["kind"],
            "description": merchant["description"] + " " + merchant["description_en"],
            "constraints": {
                "data_origin": "synthetic",
                "region": merchant["region"],
                "offering_ids": [offer["id"] for offer in merchant["offerings"]],
                "offerings": merchant["offerings"],
                "availability": "simulated_unverified",
            },
        },
    )
    validate_market_packet(packet)
    return packet


@lru_cache(maxsize=1)
def expected_catalog():
    categories, merchants = generate_catalog()
    if len(categories) != 50 or len(merchants) != 500:
        raise market_error()
    merchants = [{**merchant, "capability": capability(merchant)} for merchant in merchants]
    merchants.sort(key=lambda merchant: merchant["id"])
    offers = [offer for merchant in merchants for offer in merchant["offerings"]]
    if (
        len(offers) != 1500
        or len({offer["id"] for offer in offers}) != 1500
        or len({merchant["id"] for merchant in merchants}) != 500
        or any(len(merchant["offerings"]) != 3 for merchant in merchants)
    ):
        raise market_error()
    content_hash = hashlib.sha256(canonical([categories, merchants]).encode("utf-8")).hexdigest()
    return categories, merchants, content_hash


def _read_store(path):
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise market_error()
            metadata = dict(db.execute("SELECT key,value FROM market_metadata"))
            expected_categories, _, expected_hash = expected_catalog()
            if (
                metadata.get("store_version") != STORE_VERSION
                or metadata.get("seed_version") != SEED_VERSION
                or metadata.get("seed_date") != SEED_DATE
                or metadata.get("seed_sha256") != expected_hash
            ):
                raise market_error()
            categories = json.loads(metadata["categories_json"])
            rows = db.execute("SELECT id,data_json FROM merchants ORDER BY id").fetchall()
            merchants = [json.loads(row[1]) for row in rows]
            if any(row[0] != merchant["id"] for row, merchant in zip(rows, merchants)):
                raise market_error()
            digest = hashlib.sha256(canonical([categories, merchants]).encode("utf-8")).hexdigest()
            if categories != expected_categories or digest != expected_hash:
                raise market_error()
            return categories, merchants
    except (sqlite3.Error, ValueError, KeyError, TypeError):
        raise market_error() from None


def initialize_market(settings, *, rebuild=False):
    """Create only this store; existing corrupt/outdated data is never silently replaced."""
    path = settings.data_dir / DATABASE_NAME
    if path == settings.database:
        raise market_error()
    if path.exists() and not rebuild:
        _read_store(path)
        return path
    categories, merchants, digest = expected_catalog()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    # Exclusive sidecar creation prevents replacing an existing store unless explicitly requested.
    temporary = path.with_name(path.name + ".initializing")
    try:
        with temporary.open("xb"):
            pass
    except FileExistsError:
        raise AppError(
            "SIMULATED_MARKET_BUSY", "模拟市场初始化正在进行或需检查遗留临时文件。", 503
        ) from None
    try:
        with closing(sqlite3.connect(temporary)) as db:
            db.execute("CREATE TABLE market_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            db.execute("CREATE TABLE merchants(id TEXT PRIMARY KEY,data_json TEXT NOT NULL)")
            db.executemany(
                "INSERT INTO market_metadata VALUES (?,?)",
                [
                    ("store_version", STORE_VERSION),
                    ("seed_version", SEED_VERSION),
                    ("seed_date", SEED_DATE),
                    ("seed_sha256", digest),
                    ("categories_json", canonical(categories)),
                ],
            )
            db.executemany(
                "INSERT INTO merchants VALUES (?,?)",
                [(merchant["id"], canonical(merchant)) for merchant in merchants],
            )
            db.commit()
        _read_store(temporary)
        if rebuild:
            temporary.replace(path)
        else:
            # Windows rename refuses an existing destination, including a racing initializer.
            temporary.rename(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def _matches_alias(text, alias):
    text, alias = text.casefold(), alias.casefold()
    if re.search(r"[a-z]", alias):
        return re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text) is not None
    return len(alias) >= 2 and alias in text


def relevance(text, offer, categories):
    """Return ordering evidence only, never percentages or a requirement-satisfaction score."""
    overlap = [alias for alias in offer.get("aliases", []) if _matches_alias(text, alias)]
    specific = [alias for alias in overlap if alias.casefold() not in BROAD_ALIASES]
    category = categories[offer["category"]]
    broad = [alias for alias in category.get("aliases", []) if _matches_alias(text, alias)]
    broad += [alias for alias in overlap if alias.casefold() in BROAD_ALIASES]
    if specific:
        return 2, specific
    if broad:
        return 1, broad
    return 0, []


def public_offer(offer):
    return {key: value for key, value in offer.items() if key != "aliases"}


def budget_check(item, offer):
    budget = item.get("budget_ceiling")
    result = {"status": "unknown"}
    if not budget:
        return {
            "status": "not_provided",
            "note": "没有单项预算；整单预算不会平均分配。",
            "note_en": "No item budget. Whole-list budgets are never divided among items.",
        }
    if budget.get("confirmed") is not True or budget.get("source") == "unknown":
        result.update(note="预算尚未确认。", note_en="Budget is unconfirmed.")
        return result
    price = offer["price"]
    if budget["currency"] != price["currency"]:
        result.update(note="币种不同，未换汇比较。", note_en="Different currencies; no conversion.")
        return result
    basis = item.get("budget_basis", "unknown")
    unit = (item.get("unit") or "").casefold()
    accepted_units = {price["unit"].casefold(), price["unit_en"].casefold()}
    # No assumed conversions between a set, hour, piece, metre, square metre, etc.
    if basis not in {"unit", "line_total"} or not unit or unit not in accepted_units:
        result.update(
            note="预算或计价单位未明确/不一致，无法比较。",
            note_en="Budget basis or pricing unit is unknown or differs.",
        )
        return result
    amount = Decimal(str(price["amount"]))
    if basis == "line_total":
        quantity = item.get("quantity")
        if quantity is None or quantity <= 0:
            result.update(
                note="合计预算缺少数量，无法比较。",
                note_en="Line-total budget needs an explicit quantity.",
            )
            return result
        amount *= Decimal(str(quantity))
    limit = Decimal(str(budget["amount"]))
    result.update(
        status="within" if amount <= limit else "over",
        estimated_amount=float(amount),
        currency=price["currency"],
        basis=basis,
        note="仅比较模拟基础价格；税费、运费及配置差价未核实。",
        note_en="Synthetic base price only; taxes, shipping and options are unverified.",
    )
    return result


def proposal_for(intent_id, version_id, item, merchant, offer, reasons, gaps, timestamp):
    identity = ":".join(["proposal", intent_id, version_id, str(item["item_id"]), offer["id"]])
    packet = envelope(
        "proposal.submit",
        merchant["id"],
        identity,
        {
            "proposal_id": stable_id(identity + ":payload"),
            "target_intent_id": intent_id,
            "solution_type": offer["kind"],
            "description": "SYNTHETIC / 本地模拟：" + offer["name"] + " / " + offer["name_en"],
            "satisfies": [],
            "gaps": gaps,
            "pricing": [
                {
                    "component": offer["kind"],
                    "cost": {
                        "amount": offer["price"]["amount"],
                        "currency": offer["price"]["currency"],
                    },
                }
            ],
            "source": {
                "kind": "other",
                "description": "Deterministic synthetic catalog; no real provider",
                "observed_at": SEED_TIMESTAMP,
            },
            "promotion": {"sponsored": False, "disclosure": "Synthetic local demonstration only"},
            "ranking_explanation": "; ".join(reasons),
        },
        version_id=version_id,
        item_id=item["item_id"],
        offering_id=offer["id"],
        pricing_basis={
            "unit": offer["price"]["unit"],
            "scope": "unit_base_price",
            "quantity_not_applied": True,
        },
    )
    packet["timestamp"] = timestamp
    packet["extensions"]["demand_search_simulation_v1"]["timestamp_kind"] = "scenario_time"
    packet["intent_id"] = intent_id
    validate_market_packet(packet)
    return packet


class SimulatedMarketService:
    def __init__(self, settings):
        self.settings = settings

    def catalog(self):
        path = self.settings.data_dir / DATABASE_NAME
        if not path.exists():
            initialize_market(self.settings)
        return _read_store(path)

    def browse(self, query="", category="", page=1, page_size=12):
        if (
            not isinstance(query, str)
            or len(query) > 200
            or any(ord(char) < 32 for char in query)
            or not isinstance(page, int)
            or not 1 <= page <= 10000
            or not isinstance(page_size, int)
            or not 1 <= page_size <= 60
        ):
            raise AppError("MARKET_QUERY_INVALID", "搜索词或分页参数无效。", 422)
        categories, merchants = self.catalog()
        category_map = {value["id"]: value for value in categories}
        if category and category not in category_map:
            raise AppError("MARKET_CATEGORY_INVALID", "模拟市场分类不存在。", 422)
        ranked = []
        for merchant in merchants:
            for offer in merchant["offerings"]:
                if category and offer["category"] != category:
                    continue
                rank, _ = relevance(query, offer, category_map)
                if query.strip() and not rank:
                    haystack = " ".join(
                        [offer["name"], offer["name_en"], merchant["name"], merchant["name_en"]]
                    ).casefold()
                    if query.strip().casefold() not in haystack:
                        continue
                ranked.append((rank, offer))
        ranked.sort(
            key=lambda pair: (-pair[0], pair[1]["category"], pair[1]["name_en"], pair[1]["id"])
        )
        start = (page - 1) * page_size
        return {
            "kind": "simulated_market",
            "data_origin": "synthetic",
            "seed_version": SEED_VERSION,
            "seed_date": SEED_DATE,
            "total_merchants": 500,
            "total_offerings": 1500,
            "total": len(ranked),
            "page": page,
            "page_size": page_size,
            "categories": [
                {key: value for key, value in entry.items() if key != "aliases"}
                for entry in categories
            ],
            "items": [public_offer(pair[1]) for pair in ranked[start : start + page_size]],
            "notice": NOTICE,
            "notice_en": NOTICE_EN,
        }

    def merchant(self, identity):
        identity = checked_id(identity)
        _, merchants = self.catalog()
        merchant = next((entry for entry in merchants if entry["id"] == identity), None)
        if merchant is None:
            raise AppError("MARKET_MERCHANT_NOT_FOUND", "模拟商家不存在。", 404)
        return {**merchant, "offerings": [public_offer(offer) for offer in merchant["offerings"]]}

    def match(self, conversation_id, version_id):
        conversation_id, version_id = checked_id(conversation_id), checked_id(version_id)
        # Read-only SQLite connection: this operation cannot update a confirmed snapshot.
        with closing(sqlite3.connect(self.settings.database.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            HistoryService(self.settings)._conversation(db, conversation_id)
            row = db.execute(
                "SELECT v.id,v.number,v.status,v.data_json,d.intent_id,d.sender_id,"
                "d.status AS demand_status,"
                "d.confirmed_version_id,d.current_version_id FROM demand_versions v "
                "JOIN demands d ON v.demand_id=d.id "
                "WHERE d.conversation_id=? AND d.owner_id=? AND v.id=?",
                (conversation_id, LOCAL_OWNER, version_id),
            ).fetchone()
            if row is None:
                raise AppError("DEMAND_VERSION_NOT_FOUND", "本会话不存在该需求版本。", 404)
            if row["demand_status"] == "withdrawn":
                raise AppError("DEMAND_WITHDRAWN", "已撤回需求不能进行新的模拟匹配。", 409)
            if row["status"] != "confirmed":
                raise AppError("DEMAND_CONFIRMATION_REQUIRED", "请先确认所选清单版本。", 409)
            stored = db.execute(
                "SELECT packet_bytes FROM demand_packets WHERE version_id=? ORDER BY sequence DESC",
                (version_id,),
            ).fetchone()
            if stored is None:
                raise AppError(
                    "DEMAND_INTENT_MISSING",
                    "所选确认版本缺少本地NCP意图记录，无法生成模拟提案。",
                    409,
                )
            intent_packet = json.loads(stored["packet_bytes"])
            validate_packet(intent_packet)
            if (
                intent_packet["message_type"] not in {"intent.publish", "intent.update"}
                or intent_packet["intent_id"] != row["intent_id"]
                or intent_packet["sender"]["participant_id"] != row["sender_id"]
            ):
                raise AppError("DEMAND_INTENT_MISMATCH", "所选版本NCP意图关联不一致。", 409)
            data = json.loads(row["data_json"])
        items = data.get("items", [])
        if not isinstance(items, list) or len(items) > 30:
            raise AppError("MARKET_ITEMS_INVALID", "清单结构无效。", 422)
        if not items:
            items = [
                {
                    "item_id": None,
                    "name": data["desired_outcome"],
                    "confirmed": True,
                    "source": "user_confirmed",
                    "status": "active",
                }
            ]
        active = [item for item in items if item.get("status") == "active"]
        if not active:
            raise AppError("MARKET_ITEMS_EMPTY", "没有可匹配的有效清单项目。", 409)
        if any(
            item.get("confirmed") is not True or item.get("source") == "unknown" for item in active
        ):
            raise AppError("MARKET_ITEM_UNCONFIRMED", "请先确认每个清单项目。", 409)
        scenario_time = max(
            datetime.fromisoformat(intent_packet["timestamp"]),
            datetime.fromisoformat(SEED_TIMESTAMP),
        ) + timedelta(microseconds=1)
        scenario_timestamp = scenario_time.isoformat(timespec="microseconds").replace("+00:00", "Z")
        categories, merchants = self.catalog()
        category_map = {entry["id"]: entry for entry in categories}
        results, proposals = [], []
        for item in active:
            candidates = []
            for merchant in merchants:
                for offer in merchant["offerings"]:
                    rank, terms = relevance(item["name"], offer, category_map)
                    if rank:
                        candidates.append((rank, terms, merchant, offer))
            # Specific aliases suppress broad category-only candidates. Generic queries remain
            # explicitly broad, with deterministic ordering independent of budget/commission.
            strongest = max((entry[0] for entry in candidates), default=0)
            candidates = [entry for entry in candidates if entry[0] == strongest]
            candidates.sort(key=lambda entry: (entry[3]["name_en"], entry[3]["id"]))
            matches = []
            for rank, terms, merchant, offer in candidates[:3]:
                reasons = [
                    ("商品关键词相关：" if rank == 2 else "仅领域关键词相关：") + "、".join(terms)
                ]
                reasons_en = [
                    ("Offering keyword overlap: " if rank == 2 else "Broad category overlap only: ")
                    + ", ".join(terms)
                ]
                required = [
                    fact["text"] for fact in [*data.get("required", []), *item.get("required", [])]
                ]
                unknown = [*data.get("unknown", []), *item.get("unknown", [])]
                gaps = [
                    LIMITATION,
                    *["未核实硬约束：" + text for text in required],
                    *["尚未明确：" + text for text in unknown],
                ]
                gaps_en = [
                    LIMITATION_EN,
                    *["Unverified requirement: " + text for text in required],
                    *["Unknown: " + text for text in unknown],
                ]
                packet = proposal_for(
                    row["intent_id"],
                    version_id,
                    item,
                    merchant,
                    offer,
                    reasons_en,
                    gaps,
                    scenario_timestamp,
                )
                match = {
                    "offering": public_offer(offer),
                    "reasons": reasons,
                    "reasons_en": reasons_en,
                    "budget": budget_check(item, offer),
                    "unverified": gaps,
                    "unverified_en": gaps_en,
                    "proposal": packet,
                }
                matches.append(match)
                proposals.append(packet)
            results.append(
                {
                    "item_id": item["item_id"],
                    "name": item["name"],
                    "matches": matches,
                    "unmatched_reason": None
                    if matches
                    else "目录中没有识别到具体商品或领域关键词。",
                    "unmatched_reason_en": None
                    if matches
                    else "No recognized offering or category keywords in this synthetic catalog.",
                }
            )
        return {
            "kind": "simulated_market_matches",
            "data_origin": "synthetic",
            "version_id": version_id,
            "version_number": row["number"],
            "intent_id": row["intent_id"],
            "is_latest_confirmed": version_id == row["confirmed_version_id"],
            "is_current_version": version_id == row["current_version_id"],
            "network_searched": False,
            "notice": NOTICE + LIMITATION,
            "notice_en": NOTICE_EN + " " + LIMITATION_EN,
            "whole_list_budget": data.get("budget_ceiling"),
            "whole_list_budget_note": "整单预算仅保留，不分配到项目；没有生成或验证完整组合报价。",
            "whole_list_budget_note_en": "Whole-list budget is retained, never allocated. "
            "No complete basket quote was generated or verified.",
            "items": results,
            "proposals": proposals,
        }

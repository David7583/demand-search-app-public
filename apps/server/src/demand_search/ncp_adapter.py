"""Independent, local-only NCP intent mapping; never imports the upstream implementation."""

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from uuid import UUID, uuid4

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry
from referencing.exceptions import NoSuchResource

from .config import ROOT
from .errors import AppError

WIRE = "ODIP/0.1.3-exp.1"
SCHEMA_SHA256 = "15e59c84cbf98a4e88371695be247fd527d825c54ed2f3f1820f5b3031abafb0"
SUPPORTED = {"intent.publish", "intent.update", "intent.withdraw"}
MAX_PACKET_BYTES = 65536
MAX_DEPTH = 32
UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time")
def utc_time(value):
    if not isinstance(value, str):
        return True
    if not UTC_PATTERN.fullmatch(value):
        return False
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


@FORMAT_CHECKER.checks("uuid")
def canonical_uuid(value):
    if not isinstance(value, str):
        return True
    try:
        return str(UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _deny_reference(uri):
    raise NoSuchResource(ref=uri)


@lru_cache(maxsize=1)
def _validator():
    raw = (ROOT / "vendor/ncp/schemas/packet.schema.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SCHEMA_SHA256:
        raise AppError(
            "NCP_SCHEMA_INTEGRITY", "Pinned local NCP Schema integrity check failed", 500
        )
    schema = json.loads(raw)

    def check_refs(value):
        if isinstance(value, dict):
            if "$ref" in value and not value["$ref"].startswith("#/"):
                raise AppError(
                    "NCP_SCHEMA_REFERENCE", "Only local NCP Schema references allowed", 500
                )
            for child in value.values():
                check_refs(child)
        elif isinstance(value, list):
            for child in value:
                check_refs(child)

    check_refs(schema)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(
        schema, format_checker=FORMAT_CHECKER, registry=Registry(retrieve=_deny_reference)
    )


def _encoding(packet):
    def walk(value, depth=1):
        if depth > MAX_DEPTH:
            raise AppError("NCP_DEPTH_LIMIT", "Local NCP representation exceeds depth limit", 422)
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise AppError("NCP_INVALID_JSON", "NCP object keys must be strings", 422)
            for item in value.values():
                walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                walk(item, depth + 1)

    try:
        walk(packet)
        raw = json.dumps(
            packet, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise AppError("NCP_INVALID_JSON", "Invalid local NCP JSON representation", 422) from None
    if len(raw) > MAX_PACKET_BYTES:
        raise AppError(
            "NCP_MESSAGE_TOO_LARGE",
            "Local NCP representation exceeds 64 KiB; shorten conditions or split the list "
            "into another conversation. No data was truncated.",
            422,
        )
    return raw


def validate_schema(packet):
    """Pinned Draft 2020-12 structure with UUID and UTC date-time assertions."""
    _encoding(packet)
    if isinstance(packet, dict) and packet.get("protocol") != WIRE:
        raise AppError(
            "VERSION_UNSUPPORTED", "NCP wire identifier must match the pinned version", 422
        )
    if next(_validator().iter_errors(packet), None) is not None:
        raise AppError("SCHEMA_INVALID", "NCP message does not satisfy the pinned Schema", 422)


def _single(packet):
    validate_schema(packet)
    kind = packet["message_type"]
    if kind not in SUPPORTED:
        raise AppError(
            "NCP_MESSAGE_UNSUPPORTED", "Only local intent lifecycle messages are supported", 422
        )
    payload = packet["payload"]
    if "target_intent_id" in payload and payload["target_intent_id"] != packet["intent_id"]:
        raise AppError("ID_MISMATCH", "NCP target and envelope intent IDs differ", 422)
    if "commerce" in packet.get("extensions", {}):
        raise AppError(
            "NCP_EXTENSION_UNSUPPORTED", "Commerce semantics are not supported by this adapter", 422
        )
    intent = payload if kind == "intent.publish" else payload.get("intent")
    if intent is not None and intent["privacy"] != {
        "sharing_scope": "private",
        "allow_aggregate_analytics": False,
    }:
        raise AppError(
            "NCP_LOCAL_PRIVACY_REQUIRED",
            "This app supports only private local intent representations",
            422,
        )
    # Unknown non-critical extensions remain opaque; no execution or URL fetching.


def _apply(packet, states, seen):
    identifier = packet["message_id"]
    if identifier in seen:
        # This is an app export sequence invariant, not a transport duplicate receipt.
        raise AppError("NCP_MESSAGE_ID_REUSED", "Local export contains a reused message ID", 422)
    kind, intent_id, sender = (
        packet["message_type"],
        packet["intent_id"],
        packet["sender"]["participant_id"],
    )
    old = states.get(intent_id)
    if kind == "intent.publish":
        if old:
            raise AppError("INTENT_EXISTS", "Intent already exists in this local sequence", 422)
        states[intent_id] = {"owner": sender, "revision": 1, "active": True}
    else:
        if old is None:
            raise AppError("UNKNOWN_INTENT", "Intent has not been published in this sequence", 422)
        if old["owner"] != sender:
            raise AppError(
                "FORBIDDEN", "Intent updates and withdrawal require the same local owner", 422
            )
        if not old["active"]:
            raise AppError(
                "INTENT_WITHDRAWN", "A withdrawn intent cannot be implicitly revived", 422
            )
        if kind == "intent.update":
            if packet["payload"]["revision"] != old["revision"] + 1:
                raise AppError("REVISION_CONFLICT", "NCP revisions must be contiguous", 422)
            old["revision"] += 1
        else:
            old["active"] = False
    seen.add(identifier)


def validate_sequence(packets):
    """Validate supplied stored history without mutating any packet or external state."""
    if not isinstance(packets, (list, tuple)) or len(packets) > 1000:
        raise AppError("NCP_HISTORY_LIMIT", "Expected at most 1000 local NCP history packets", 422)
    states, seen = {}, set()
    for packet in packets:
        _single(packet)
        _apply(packet, states, seen)


def validate_packet(packet, *, previous=None):
    """None means single-packet validation; [] means a new stateful history."""
    _single(packet)
    if previous is not None:
        if not isinstance(previous, (list, tuple)):
            raise AppError("NCP_HISTORY_INVALID", "Prior packets must be a sequence", 422)
        validate_sequence([*previous, packet])


def serialize_packet(packet):
    """Stable bytes for initial local storage. Export stored bytes; do not rebuild retries."""
    validate_packet(packet)
    return _encoding(packet)


def parse_packet(raw):
    """Local round trip only; not a network transport or authentication endpoint."""
    if not isinstance(raw, bytes):
        raise AppError("NCP_INVALID_JSON", "Expected UTF-8 bytes", 422)
    if len(raw) > MAX_PACKET_BYTES:
        raise AppError(
            "NCP_MESSAGE_TOO_LARGE",
            "Local NCP representation exceeds 64 KiB; shorten conditions or split the list "
            "into another conversation. No data was truncated.",
            422,
        )

    def no_constants(_):
        raise ValueError

    def no_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    try:
        packet = json.loads(
            raw.decode("utf-8"), parse_constant=no_constants, object_pairs_hook=no_duplicates
        )
    except (ValueError, UnicodeError, RecursionError):
        raise AppError("NCP_INVALID_JSON", "Invalid UTF-8 JSON or duplicate keys", 422) from None
    validate_packet(packet)
    return packet


def map_intent(original_text, content, *, user_confirmed):
    """Map confirmed app data; application facts stay namespaced and provenance stays explicit."""
    if user_confirmed is not True:
        raise AppError(
            "DEMAND_CONFIRMATION_REQUIRED", "Confirm the demand before creating NCP data", 409
        )
    if not isinstance(content, dict):
        raise AppError("NCP_MAPPING_INVALID", "Expected a confirmed demand object", 422)
    if not isinstance(content.get("alternatives_acceptable"), bool):
        raise AppError(
            "NCP_ALTERNATIVES_REQUIRED",
            "Explicitly choose whether alternatives are acceptable",
            422,
        )
    facts = {
        key: copy.deepcopy(content.get(key, []))
        for key in ("required", "preferred", "unknown", "clarification_questions")
    }
    facts["format"] = "demand-search-app.intent-facts/1"
    if content.get("items"):
        facts["shopping_list"] = {
            "format": "demand-search-app.shopping-list/1",
            "budget_scope": "whole_list",
            "items": copy.deepcopy(content["items"]),
        }
    facts["possible_new_intent"] = bool(content.get("possible_new_intent", False))
    budget = content.get("budget_ceiling")
    constraints = {"specifications": {"demand_search_app_v1": facts}}
    if budget is not None:
        if not isinstance(budget, dict):
            raise AppError("NCP_MAPPING_INVALID", "Budget must retain its source declaration", 422)
        facts["budget_annotation"] = copy.deepcopy(budget)
        if budget.get("confirmed") is True and budget.get("source") != "unknown":
            constraints["budget_ceiling"] = {
                "amount": budget.get("amount"),
                "currency": budget.get("currency"),
            }
    result = {
        "original_text": original_text,
        "desired_outcome": content.get("desired_outcome"),
        "readiness": content.get("readiness"),
        "alternatives_acceptable": content["alternatives_acceptable"],
        "user_confirmed": True,
        "constraints": constraints,
        "privacy": {"sharing_scope": "private", "allow_aggregate_analytics": False},
        "interpretation_notes": (
            "Confirmed app snapshot; per-field sources, uncertainty and confirmation flags "
            "remain in specifications.demand_search_app_v1, an application convention, not "
            "standard NCP constraint semantics. No purchase or sharing authorization."
        ),
    }
    return result


def build_packet(
    message_type,
    *,
    intent_id,
    sender_id,
    intent=None,
    revision=None,
    reason=None,
    message_id=None,
    timestamp=None,
):
    if message_type not in SUPPORTED:
        raise AppError("NCP_MESSAGE_UNSUPPORTED", "Unsupported local message type", 422)
    if message_type == "intent.publish":
        payload = copy.deepcopy(intent)
    elif message_type == "intent.update":
        payload = {
            "target_intent_id": intent_id,
            "revision": revision,
            "intent": copy.deepcopy(intent),
        }
    else:
        payload = {"target_intent_id": intent_id}
        if reason is not None:
            payload["reason"] = reason
    packet = {
        "protocol": WIRE,
        "message_id": message_id or str(uuid4()),
        "message_type": message_type,
        "timestamp": timestamp
        or datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "sender": {"participant_id": sender_id},
        "intent_id": intent_id,
        "payload": payload,
    }
    validate_packet(packet)
    return packet

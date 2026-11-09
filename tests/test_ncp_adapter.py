"""Independent NCP application profile tests; all inputs and identities are synthetic."""

import copy
import hashlib
import json
import socket
from uuid import uuid4

import pytest
from demand_search.config import ROOT
from demand_search.errors import AppError
from demand_search.ncp_adapter import (
    WIRE,
    _validator,
    build_packet,
    map_intent,
    parse_packet,
    serialize_packet,
    validate_packet,
    validate_schema,
    validate_sequence,
)

VENDOR = ROOT / "vendor/ncp"
SELECTED = json.loads((VENDOR / "selected-cases.json").read_text(encoding="utf-8"))["vectors"]


def content():
    return {
        "desired_outcome": "A synthetic safe workspace",
        "readiness": "need",
        "alternatives_acceptable": True,
        "required": [
            {"text": "safe", "source": "user_explicit", "evidence": "safe", "confirmed": True}
        ],
        "preferred": [
            {"text": "quiet", "source": "model_inferred", "evidence": "", "confirmed": False}
        ],
        "unknown": ["dimensions"],
        "budget_ceiling": {
            "amount": 1500,
            "currency": "CNY",
            "source": "user_confirmed",
            "evidence": "User explicitly confirmed ceiling",
            "confirmed": True,
        },
        "clarification_questions": ["Which dimensions?"],
        "possible_new_intent": False,
    }


def publication(**kwargs):
    return build_packet(
        "intent.publish",
        intent_id="synthetic-intent",
        sender_id="synthetic-owner",
        intent=map_intent(
            "Original safe need with newline\nUnchanged.", content(), user_confirmed=True
        ),
        **kwargs,
    )


def updated(previous, revision=2, sender="synthetic-owner"):
    data = copy.deepcopy(previous["payload"])
    data["constraints"]["budget_ceiling"]["amount"] = 3000
    return build_packet(
        "intent.update",
        intent_id=previous["intent_id"],
        sender_id=sender,
        revision=revision,
        intent=data,
    )


def code_is(code, function, *args, **kwargs):
    with pytest.raises(AppError) as exc:
        function(*args, **kwargs)
    assert exc.value.code == code


@pytest.mark.parametrize("case", SELECTED, ids=lambda case: case["id"])
def test_selected_upstream_schema_vectors(case):
    packet = json.loads((VENDOR / "conformance" / case["file"]).read_text(encoding="utf-8"))
    if case["schema_valid"]:
        validate_schema(packet)
    else:
        code_is(
            "VERSION_UNSUPPORTED" if case["id"] == "bad-version" else "SCHEMA_INVALID",
            validate_schema,
            packet,
        )


def test_imported_asset_hashes_and_no_upstream_runtime_code():
    lock = json.loads((ROOT / "config/ncp-import-lock.json").read_text(encoding="utf-8"))
    assert len(lock["files"]) == 21 and lock["selected_vector_count"] == 15
    assert not lock["upstream_implementation_imported"]
    for item in lock["files"]:
        assert hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() == item["sha256"]
        assert item["modified"] is False
    assert not list(VENDOR.rglob("*.py"))


def test_mapping_preserves_raw_text_provenance_privacy_and_budget():
    source = content()
    snapshot = copy.deepcopy(source)
    raw = "  Synthetic raw words\r\nBudget 1500\u3002 "
    mapped = map_intent(raw, source, user_confirmed=True)
    assert mapped["original_text"] == raw
    assert mapped["privacy"] == {"sharing_scope": "private", "allow_aggregate_analytics": False}
    assert mapped["constraints"]["budget_ceiling"] == {"amount": 1500, "currency": "CNY"}
    facts = mapped["constraints"]["specifications"]["demand_search_app_v1"]
    assert facts["preferred"][0]["source"] == "model_inferred"
    assert facts["preferred"][0]["confirmed"] is False
    assert facts["unknown"] == ["dimensions"]
    facts["required"].clear()
    assert source == snapshot
    assert mapped["user_confirmed"] is True


@pytest.mark.parametrize("source,confirmed", [("model_inferred", False), ("unknown", True)])
def test_unconfirmed_or_unknown_budget_is_not_a_core_hard_constraint(source, confirmed):
    draft = content()
    draft["budget_ceiling"].update(source=source, confirmed=confirmed)
    mapped = map_intent("Synthetic input", draft, user_confirmed=True)
    assert "budget_ceiling" not in mapped["constraints"]
    note = mapped["constraints"]["specifications"]["demand_search_app_v1"]["budget_annotation"]
    assert note["source"] == source and note["confirmed"] is confirmed


def test_no_budget_is_omitted_not_zero():
    data = content()
    data["budget_ceiling"] = None
    mapped = map_intent("Synthetic input", data, user_confirmed=True)
    assert "budget_ceiling" not in mapped["constraints"]


@pytest.mark.parametrize("confirmed", [False, None, 1, "true"])
def test_mapping_cannot_upgrade_unconfirmed_version(confirmed):
    code_is(
        "DEMAND_CONFIRMATION_REQUIRED", map_intent, "Synthetic", content(), user_confirmed=confirmed
    )


@pytest.mark.parametrize("alternatives", [None, 0, "", "false"])
def test_unknown_alternatives_require_explicit_choice(alternatives):
    data = content()
    data["alternatives_acceptable"] = alternatives
    code_is("NCP_ALTERNATIVES_REQUIRED", map_intent, "Synthetic", data, user_confirmed=True)


def test_local_lifecycle_and_immutable_old_budget_round_trip():
    first = publication()
    before = copy.deepcopy(first)
    second = updated(first)
    third = build_packet(
        "intent.withdraw",
        intent_id=first["intent_id"],
        sender_id="synthetic-owner",
        reason="Synthetic withdrawal; not an order cancellation",
    )
    validate_sequence([first, second, third])
    validate_packet(second, previous=[first])
    assert first == before and first["payload"]["constraints"]["budget_ceiling"]["amount"] == 1500
    assert second["payload"]["intent"]["constraints"]["budget_ceiling"]["amount"] == 3000
    for packet in (first, second, third):
        raw = serialize_packet(packet)
        assert raw == serialize_packet(packet)
        assert parse_packet(raw) == packet
        assert packet["protocol"] == WIRE
    assert len({p["message_id"] for p in (first, second, third)}) == 3


def test_unknown_owner_revision_and_withdrawal_state():
    first = publication()
    second = updated(first)
    code_is("UNKNOWN_INTENT", validate_packet, second, previous=[])
    code_is(
        "FORBIDDEN", validate_packet, updated(first, sender="synthetic-other"), previous=[first]
    )
    code_is("REVISION_CONFLICT", validate_packet, updated(first, revision=3), previous=[first])
    withdrawn = build_packet(
        "intent.withdraw", intent_id=first["intent_id"], sender_id="synthetic-owner"
    )
    code_is("INTENT_WITHDRAWN", validate_packet, second, previous=[first, withdrawn])
    code_is("INTENT_EXISTS", validate_packet, publication(), previous=[first])
    code_is("NCP_MESSAGE_ID_REUSED", validate_sequence, [first, first])


def test_cross_field_mismatch_and_reused_message_id():
    first = publication()
    second = updated(first)
    second["payload"]["target_intent_id"] = "synthetic-other"
    code_is("ID_MISMATCH", validate_packet, second, previous=[first])
    second = updated(first)
    second["message_id"] = first["message_id"]
    code_is("NCP_MESSAGE_ID_REUSED", validate_packet, second, previous=[first])


@pytest.mark.parametrize(
    "scope,analytics", [("public", False), ("selected_participants", False), ("private", True)]
)
def test_app_cannot_silently_grant_disclosure_or_aggregation(scope, analytics):
    packet = publication()
    packet["payload"]["privacy"] = {"sharing_scope": scope, "allow_aggregate_analytics": analytics}
    validate_schema(packet)  # Valid NCP; deliberately unsupported by this private app profile.
    code_is("NCP_LOCAL_PRIVACY_REQUIRED", validate_packet, packet)


def test_private_vector_has_different_local_and_network_meaning():
    packet = json.loads(
        (VENDOR / "conformance/vectors/private-network-intent.json").read_text(encoding="utf-8")
    )
    validate_packet(
        packet
    )  # Local representation only: do not apply upstream network refusal here.
    case = next(c for c in SELECTED if c["id"] == "private-network-intent")
    assert case["expected_code"] == "PRIVACY_DENIED"


def test_unknown_extension_is_opaque_and_validation_is_offline(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("No network resolution allowed")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    _validator.cache_clear()
    packet = publication()
    packet["extensions"] = {
        "org.example.opaque": {"url": "https://example.invalid/do-not-fetch", "script": "opaque"}
    }
    snapshot = copy.deepcopy(packet)
    validate_sequence([packet])
    assert packet == snapshot and parse_packet(serialize_packet(packet)) == packet


@pytest.mark.parametrize(
    "value",
    [
        "2026-02-30T00:00:00Z",
        "2026-11-04T23:59:60Z",
        "2026-11-04t00:00:00z",
        "2026-11-04T00:00:00+00:00",
        "2026-11-04T00:00:00.1234567Z",
        "0000-01-01T00:00:00Z",
    ],
)
def test_strict_utc_format_assertions(value):
    packet = publication()
    packet["timestamp"] = value
    code_is("SCHEMA_INVALID", validate_schema, packet)


@pytest.mark.parametrize("amount", [True, -1, "1500"])
def test_budget_type_not_silently_coerced(amount):
    packet = publication()
    packet["payload"]["constraints"]["budget_ceiling"]["amount"] = amount
    code_is("SCHEMA_INVALID", validate_schema, packet)


@pytest.mark.parametrize(
    "raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b"\xef\xbb\xbf{}", b"\xff", b"{} trailing"]
)
def test_invalid_utf8_duplicate_json_and_nonfinite_rejected(raw):
    code_is("NCP_INVALID_JSON", parse_packet, raw)


def test_bounded_input_and_no_unpaired_surrogate():
    packet = publication()
    packet["payload"]["original_text"] = "x" * 65536
    code_is("NCP_MESSAGE_TOO_LARGE", serialize_packet, packet)
    code_is("NCP_MESSAGE_TOO_LARGE", parse_packet, b" " * 65537)
    packet = publication()
    packet["payload"]["original_text"] = "\ud800"
    code_is("NCP_INVALID_JSON", serialize_packet, packet)
    packet = publication()
    branch = packet.setdefault("extensions", {})
    for _ in range(34):
        branch["deep"] = {}
        branch = branch["deep"]
    code_is("NCP_DEPTH_LIMIT", serialize_packet, packet)
    packet = publication()
    packet["payload"]["constraints"]["budget_ceiling"]["amount"] = float("nan")
    code_is("NCP_INVALID_JSON", serialize_packet, packet)


def test_other_valid_core_type_not_mistaken_for_supported_adapter():
    packet = {
        "protocol": WIRE,
        "message_id": str(uuid4()),
        "message_type": "capability.advertise",
        "timestamp": "2026-11-04T00:00:00Z",
        "sender": {"participant_id": "synthetic"},
        "payload": {"kind": "analysis", "description": "Synthetic only"},
    }
    validate_schema(packet)
    code_is("NCP_MESSAGE_UNSUPPORTED", validate_packet, packet)

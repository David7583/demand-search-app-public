"""Bounded synthetic-market checks; no real users, credentials, AI or outbound calls."""

import copy
import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest
from demand_search.config import ROOT, Settings
from demand_search.errors import AppError
from demand_search.history_service import HistoryService
from demand_search.main import create_app
from demand_search.market_catalog import generate_catalog
from demand_search.ncp_adapter import build_packet, map_intent, validate_packet
from demand_search.simulated_market import (
    DATABASE_NAME,
    PRIVACY,
    SimulatedMarketService,
    budget_check,
    expected_catalog,
    initialize_market,
    relevance,
    validate_market_packet,
)
from demand_search.storage import connect, initialize
from fastapi.testclient import TestClient


def uid():
    return str(uuid4())


@pytest.fixture
def setup():
    folder = ROOT / "runtime" / ("test-synthetic-" + uuid4().hex)
    settings = Settings(data_dir=folder)
    initialize(settings)
    history = HistoryService(settings)
    conversation = history.create("SYNTHETIC market test")["id"]
    message = history.add_message(conversation, "PRIVATE ORIGINAL TEST TEXT", uid())["message"]
    demand, intent, sender, version, draft = (uid() for _ in range(5))
    stamp = "2026-11-09T00:00:00Z"
    content = {
        "desired_outcome": "Synthetic workspace",
        "readiness": "want",
        "alternatives_acceptable": True,
        "required": [
            {
                "text": "PRIVATE REQUIREMENT: zero noise",
                "confirmed": True,
                "source": "user_confirmed",
            }
        ],
        "preferred": [],
        "unknown": ["PRIVATE UNKNOWN"],
        "budget_ceiling": {
            "amount": 2500,
            "currency": "CNY",
            "confirmed": True,
            "source": "user_confirmed",
        },
        "items": [
            {
                "item_id": uid(),
                "name": "办公椅",
                "status": "active",
                "confirmed": True,
                "source": "user_confirmed",
                "quantity": 2,
                "unit": "把",
            },
            {
                "item_id": uid(),
                "name": "zxq-unrecognized",
                "status": "active",
                "confirmed": True,
                "source": "user_confirmed",
            },
            {
                "item_id": uid(),
                "name": "台灯",
                "status": "removed",
                "confirmed": True,
                "source": "user_confirmed",
            },
        ],
    }
    packet = build_packet(
        "intent.publish",
        intent_id=intent,
        sender_id=sender,
        intent=map_intent(message["content"], content, user_confirmed=True),
    )
    with connect(settings) as db:
        db.execute(
            "INSERT INTO demands VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                demand,
                conversation,
                "local",
                intent,
                sender,
                "active",
                draft,
                version,
                1,
                stamp,
                stamp,
            ),
        )
        for identity, number, status in [(version, 1, "confirmed"), (draft, 2, "draft")]:
            db.execute(
                "INSERT INTO demand_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    demand,
                    number,
                    None,
                    message["id"],
                    message["content"],
                    json.dumps(content),
                    status,
                    "synthetic",
                    "custom",
                    "synthetic/1",
                    stamp,
                ),
            )
        db.execute(
            "INSERT INTO demand_packets VALUES (?,?,?,?,?,?)",
            (packet["message_id"], demand, version, 1, json.dumps(packet).encode(), stamp),
        )
    value = dict(
        settings=settings,
        service=SimulatedMarketService(settings),
        conversation=conversation,
        version=version,
        draft=draft,
        content=content,
        intent=intent,
        demand=demand,
        history=history,
    )
    try:
        yield value
    finally:
        assert folder.resolve().is_relative_to((ROOT / "runtime").resolve())
        shutil.rmtree(folder)


def test_exact_seed_coverage_determinism_and_all_500_capabilities():
    categories, merchants, digest = expected_catalog()
    first = generate_catalog()
    assert first == generate_catalog()
    assert len(categories) == 50 and len(merchants) == 500 and len(digest) == 64
    assert all(sum(m["category"] == c["id"] for m in merchants) == 10 for c in categories)
    offerings = [offer for merchant in merchants for offer in merchant["offerings"]]
    assert len(offerings) == len({offer["id"] for offer in offerings}) == 1500
    assert all(len({offer["name"] for offer in m["offerings"]}) == 3 for m in merchants)
    assert all(
        offer["data_origin"] == offer["price"]["data_origin"] == "synthetic" for offer in offerings
    )
    for merchant in merchants:
        packet = merchant["capability"]
        validate_market_packet(packet)
        assert packet["message_type"] == "capability.advertise"
        assert packet["sender"]["participant_id"] == merchant["id"]
        assert packet["extensions"]["demand_search_simulation_v1"]["privacy"] == PRIVACY


def test_initialization_idempotency_integrity_and_explicit_rebuild(setup):
    settings = setup["settings"]
    path = initialize_market(settings)
    before = path.read_bytes()
    assert initialize_market(settings) == path
    assert path.read_bytes() == before
    assert SimulatedMarketService(settings).browse()["total_merchants"] == 500
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE market_metadata SET value='wrong' WHERE key='seed_version'")
        db.commit()
    corrupted = path.read_bytes()
    with pytest.raises(AppError):
        initialize_market(settings)
    assert path.read_bytes() == corrupted
    initialize_market(settings, rebuild=True)
    assert setup["service"].browse()["total"] == 1500
    assert path != settings.database


def test_search_pagination_aliases_unknowns_and_boundaries(setup):
    service = setup["service"]
    page = service.browse(page_size=12)
    assert len(page["items"]) == 12 and page["total"] == 1500
    second = service.browse(page=2)
    assert not {x["id"] for x in page["items"]} & {x["id"] for x in second["items"]}
    for term in ["办公椅", "台灯", "laptop"]:
        result = service.browse(query=term)
        assert result["total"] > 0
    categories, merchants, _ = expected_catalog()
    generic = [
        relevance("computer", offer, {c["id"]: c for c in categories})[0]
        for merchant in merchants
        for offer in merchant["offerings"]
    ]
    assert max(generic) == 1
    category = page["categories"][0]["id"]
    assert service.browse(category=category)["total"] == 30
    assert service.browse(query="zxq-unrecognized")["total"] == 0
    assert service.browse(page=10000)["items"] == []
    for kwargs in [
        {"query": "x" * 201},
        {"query": "\x00"},
        {"category": "fake"},
        {"page": 0},
        {"page_size": 61},
    ]:
        with pytest.raises(AppError):
            service.browse(**kwargs)


def test_proposals_link_confirmed_intent_without_network_or_snapshot_mutation(setup, monkeypatch):
    import socket

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Synthetic matching must never use the network")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    s = setup
    path = initialize_market(s["settings"])
    main_before = hashlib.sha256(s["settings"].database.read_bytes()).hexdigest()
    market_before = path.read_bytes()
    result = s["service"].match(s["conversation"], s["version"])
    assert result["network_searched"] is False
    assert result["version_id"] == s["version"] and result["intent_id"] == s["intent"]
    assert len(result["items"]) == 2 and len(result["items"][0]["matches"]) == 3
    assert result["items"][1]["matches"] == [] and result["items"][1]["unmatched_reason"]
    assert result["items"][0]["matches"][0]["budget"]["status"] == "not_provided"
    assert result["whole_list_budget"]["amount"] == 2500
    for packet in result["proposals"]:
        validate_market_packet(packet)
        assert packet["intent_id"] == packet["payload"]["target_intent_id"] == s["intent"]
        ext = packet["extensions"]["demand_search_simulation_v1"]
        assert (
            ext["version_id"] == s["version"]
            and ext["item_id"] == s["content"]["items"][0]["item_id"]
        )
        assert ext["timestamp_kind"] == "scenario_time"
        assert packet["timestamp"] > "2026-11-09T00:00:00.000000Z"
        assert packet["payload"]["satisfies"] == []
        assert any("PRIVATE REQUIREMENT" in text for text in packet["payload"]["gaps"])
    assert main_before == hashlib.sha256(s["settings"].database.read_bytes()).hexdigest()
    assert path.read_bytes() == market_before and b"PRIVATE" not in path.read_bytes()
    assert s["service"].match(s["conversation"], s["version"]) == result


def test_confirmed_version_conversation_owner_withdrawn_and_intent_guards(setup):
    s = setup
    service = s["service"]
    with pytest.raises(AppError) as error:
        service.match(s["conversation"], s["draft"])
    assert error.value.code == "DEMAND_CONFIRMATION_REQUIRED"
    other = s["history"].create("SYNTHETIC other")["id"]
    with pytest.raises(AppError) as error:
        service.match(other, s["version"])
    assert error.value.code == "DEMAND_VERSION_NOT_FOUND"
    with connect(s["settings"]) as db:
        db.execute("UPDATE demands SET owner_id='other' WHERE id=?", (s["demand"],))
    with pytest.raises(AppError):
        service.match(s["conversation"], s["version"])
    with connect(s["settings"]) as db:
        db.execute(
            "UPDATE demands SET owner_id='local',status='withdrawn' WHERE id=?", (s["demand"],)
        )
    with pytest.raises(AppError) as error:
        service.match(s["conversation"], s["version"])
    assert error.value.code == "DEMAND_WITHDRAWN"
    with connect(s["settings"]) as db:
        db.execute("UPDATE demands SET status='active' WHERE id=?", (s["demand"],))
        db.execute("DELETE FROM demand_packets")
    with pytest.raises(AppError) as error:
        service.match(s["conversation"], s["version"])
    assert error.value.code == "DEMAND_INTENT_MISSING"


def test_budget_currency_quantity_and_basis_remain_conservative():
    offer = {"price": {"amount": 120, "currency": "CNY", "unit": "把", "unit_en": "chair"}}
    item = {
        "quantity": 3,
        "unit": "把",
        "budget_basis": "line_total",
        "budget_ceiling": {
            "amount": 350,
            "currency": "CNY",
            "confirmed": True,
            "source": "user_confirmed",
        },
    }
    assert budget_check(item, offer)["status"] == "over"
    assert budget_check(item, offer)["estimated_amount"] == 360
    item["budget_basis"] = "unit"
    assert budget_check(item, offer)["status"] == "within"
    for change in [
        {"unit": None},
        {"unit": "set"},
        {"budget_basis": "unknown"},
        {"budget_basis": "line_total", "quantity": None},
    ]:
        assert budget_check({**item, **change}, offer)["status"] == "unknown"
    for change in [{"currency": "USD"}, {"confirmed": False}, {"source": "unknown"}]:
        changed = {**item, "budget_ceiling": {**item["budget_ceiling"], **change}}
        assert budget_check(changed, offer)["status"] == "unknown"
    assert budget_check({}, offer)["status"] == "not_provided"


def test_market_schema_privacy_and_intent_adapter_whitelist_are_separate():
    packet = copy.deepcopy(expected_catalog()[1][0]["capability"])
    with pytest.raises(AppError) as error:
        validate_packet(packet)
    assert error.value.code == "NCP_MESSAGE_UNSUPPORTED"
    packet["extensions"]["demand_search_simulation_v1"]["privacy"]["sharing_scope"] = "public"
    with pytest.raises(AppError):
        validate_market_packet(packet)
    packet = copy.deepcopy(expected_catalog()[1][0]["capability"])
    packet["timestamp"] = "invalid"
    with pytest.raises(AppError):
        validate_market_packet(packet)


def test_routes_need_session_and_csrf_but_no_model_key(setup):
    s = setup
    with TestClient(
        create_app(s["settings"]), base_url="http://127.0.0.1", client=("127.0.0.1", 44000)
    ) as client:
        assert client.get("/api/v1/simulated-market").status_code == 401
        csrf = client.get("/api/v1/session").json()["csrf_token"]
        page = client.get("/api/v1/simulated-market").json()
        assert page["total_merchants"] == 500
        assert client.get("/api/v1/simulated-market?page=0").status_code == 422
        merchant_id = page["items"][0]["merchant_id"]
        detail = client.get("/api/v1/simulated-market/merchants/" + merchant_id)
        assert (
            detail.status_code == 200
            and detail.json()["capability"]["message_type"] == "capability.advertise"
        )
        route = f"/api/v1/conversations/{s['conversation']}/demand/simulated-market"
        assert client.post(route, json={"version_id": s["version"]}).status_code == 403
        result = client.post(route, json={"version_id": s["version"]}, headers={"x-dsa-csrf": csrf})
        assert result.status_code == 200 and result.json()["proposals"]
        assert DATABASE_NAME == "simulated-market.sqlite3"

"""S2 synthetic demand/approval/immutability tests. Never read the live runtime."""

import copy
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from demand_search.config import ROOT, Settings
from demand_search.demand_routes import create_demand_router
from demand_search.demand_service import DemandService
from demand_search.errors import AppError
from demand_search.history_service import HistoryService
from demand_search.storage import connect, initialize
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


def uid():
    return str(uuid4())


def data(amount=1500):
    return {
        "desired_outcome": "A quiet synthetic computer",
        "required": [{"text": "quiet", "source": "user_explicit", "evidence": "quiet"}],
        "preferred": [{"text": "small", "source": "model_inferred", "evidence": ""}],
        "unknown": ["power consumption"],
        "budget_ceiling": {
            "amount": amount,
            "currency": "CNY",
            "source": "user_explicit",
            "evidence": str(amount),
        },
        "readiness": "exploring",
        "alternatives_acceptable": None,
        "clarification_questions": ["Which room?"],
        "possible_new_intent": False,
    }


class Models:
    def __init__(self):
        self.calls = []
        self.output = data()
        self.callback = None

    def parse_demand(self, text, context, consent, config_id=None):
        self.calls.append((text, copy.deepcopy(context)))
        if self.callback:
            self.callback()
        return {
            "actual_model": "synthetic-model",
            "provider": "custom",
            "prompt_version": "synthetic-test/1",
            "parsed": {
                **copy.deepcopy(self.output),
                "original_text": text,
                "user_confirmed": False,
            },
        }


@pytest.fixture
def setup():
    folder = ROOT / "runtime" / ("test-demand-" + uuid4().hex)
    settings = Settings(data_dir=folder)
    initialize(settings)
    models = Models()
    yield DemandService(settings, models), HistoryService(settings), models
    assert folder.resolve().is_relative_to((ROOT / "runtime").resolve())
    shutil.rmtree(folder)


def parse(service, history, conversation, text="Need a quiet computer under 1500.", expected=None):
    message = history.add_message(conversation, text, uid())["message"]
    request = {
        "request_id": uid(),
        "message_id": message["id"],
        "expected_version_id": expected,
        "consent": True,
    }
    return service.parse(conversation, request), request


def confirmation(version):
    value = version["data"]
    budget = value["budget_ceiling"]
    return {
        "request_id": uid(),
        "version_id": version["id"],
        "confirm": True,
        "continue_current_intent": False,
        "edits": {
            "desired_outcome": value["desired_outcome"],
            "required": [v["text"] for v in value["required"]],
            "preferred": [v["text"] for v in value["preferred"]],
            "unknown": value["unknown"],
            "budget_ceiling": ({k: budget[k] for k in ("amount", "currency")} if budget else None),
            "readiness": value["readiness"],
            "alternatives_acceptable": True,
        },
    }


def test_budget_revision_preserves_original_versions_and_ncp_bytes(setup):
    service, history, models = setup
    a = history.create()["id"]
    initial_text = "  Need a quiet computer under 1500.\nPreserve this.  "
    draft, _ = parse(service, history, a, initial_text)
    assert draft["current_version"]["status"] == "draft"
    assert service.export(a, True)["packets"] == []
    first = service.confirm(a, confirmation(draft["current_version"]))
    frozen = copy.deepcopy(first["current_version"])
    request = confirmation(first["current_version"])
    request["edits"]["budget_ceiling"]["amount"] = 3000
    updated = service.confirm(a, request)
    assert updated["current_version"]["number"] == 3
    assert updated["current_version"]["data"]["budget_ceiling"]["source"] == "user_confirmed"
    assert updated["versions"][1] == frozen
    assert all(v["original_text"] == initial_text for v in updated["versions"])
    packet = service.export(a, True)
    assert [p["message_type"] for p in packet["packets"]] == ["intent.publish", "intent.update"]
    assert packet["packets"][1]["payload"]["revision"] == 2
    assert (
        packet["packets"][1]["payload"]["intent"]["constraints"]["budget_ceiling"]["amount"] == 3000
    )
    assert service.export(a, True)["packet_utf8"] == packet["packet_utf8"]
    assert models.calls[0][1] == {
        "confirmed_demand": None,
        "current_draft": None,
        "recent_messages": [],
    }


def test_ai_context_is_bounded_and_cross_conversation_isolated(setup):
    service, history, models = setup
    a, b = history.create()["id"], history.create()["id"]
    history.add_message(b, "SECRET-SYNTHETIC-B", uid())
    initial, _ = parse(service, history, a)
    approved = service.confirm(a, confirmation(initial["current_version"]))
    for _ in range(8):
        history.add_message(a, "x" * 2000, uid())
    models.output = data(3000)
    newer, _ = parse(
        service, history, a, "Change budget to 3000.", approved["current_version"]["id"]
    )
    context = models.calls[-1][1]
    assert context["confirmed_demand"]["budget_ceiling"]["amount"] == 1500
    assert len(context["recent_messages"]) <= 6
    assert sum(len(v["content"]) for v in context["recent_messages"]) <= 6000
    assert "SECRET-SYNTHETIC-B" not in json.dumps(context)
    assert newer["confirmed_version"]["id"] == approved["current_version"]["id"]
    assert service.get(b)["demand"] is None


def test_parse_and_confirm_idempotency_and_conflicts(setup):
    service, history, models = setup
    a, b = history.create()["id"], history.create()["id"]
    first, request = parse(service, history, a)
    repeated = service.parse(a, request)
    assert repeated["duplicate"] and len(models.calls) == 1
    with pytest.raises(AppError, match="REQUEST_ID_CONFLICT"):
        service.parse(b, request)
    request_changed = {**request, "config_id": uid()}
    with pytest.raises(AppError, match="REQUEST_ID_CONFLICT"):
        service.parse(a, request_changed)
    confirm = confirmation(first["current_version"])
    one = service.confirm(a, confirm)
    two = service.confirm(a, confirm)
    assert two["duplicate"] and one["result_version_id"] == two["result_version_id"]
    assert len(two["versions"]) == 2


def test_failed_model_preserves_confirmed_and_same_request_can_retry(setup):
    service, history, models = setup
    a = history.create()["id"]
    initial, _ = parse(service, history, a)
    confirmed = service.confirm(a, confirmation(initial["current_version"]))
    message = history.add_message(a, "new requirement", uid())["message"]
    request = {
        "request_id": uid(),
        "message_id": message["id"],
        "consent": True,
        "expected_version_id": confirmed["current_version"]["id"],
    }

    def failed():
        raise AppError("PROVIDER_TIMEOUT", "synthetic failure", 504)

    models.callback = failed
    with pytest.raises(AppError, match="PROVIDER_TIMEOUT"):
        service.parse(a, request)
    assert service.get(a) == {
        k: confirmed[k] for k in ("demand", "versions", "current_version", "confirmed_version")
    }
    models.callback = None
    assert not service.parse(a, request)["duplicate"]


def test_cross_message_and_old_message_cannot_be_parsed(setup):
    service, history, models = setup
    a, b = history.create()["id"], history.create()["id"]
    foreign = history.add_message(b, "foreign", uid())["message"]
    request = {
        "request_id": uid(),
        "message_id": foreign["id"],
        "consent": True,
        "expected_version_id": None,
    }
    with pytest.raises(AppError, match="MESSAGE_NOT_FOUND"):
        service.parse(a, request)
    old = history.add_message(a, "old", uid())["message"]
    history.add_message(a, "new", uid())
    request.update(request_id=uid(), message_id=old["id"])
    with pytest.raises(AppError, match="STALE_MESSAGE"):
        service.parse(a, request)
    assert models.calls == []


def test_late_model_response_cannot_overwrite_new_message_or_deleted_conversation(setup):
    service, history, models = setup
    a = history.create()["id"]
    models.callback = lambda: history.add_message(a, "new input during parse", uid())
    with pytest.raises(AppError, match="STALE_ANALYSIS"):
        parse(service, history, a)
    assert service.get(a)["demand"] is None
    models.callback = lambda: history.delete(a)
    with pytest.raises(AppError, match="CONVERSATION_NOT_FOUND"):
        parse(service, history, a)


def test_inflight_duplicate_and_lease_recovery(setup):
    service, history, models = setup
    a = history.create()["id"]
    message = history.add_message(a, "quiet", uid())["message"]
    request = {
        "request_id": uid(),
        "message_id": message["id"],
        "consent": True,
        "expected_version_id": None,
    }
    entered, release = threading.Event(), threading.Event()

    def wait():
        entered.set()
        assert release.wait(timeout=5)

    models.callback = wait
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service.parse, a, request)
        assert entered.wait(timeout=5)
        with pytest.raises(AppError, match="REQUEST_IN_PROGRESS"):
            service.parse(a, request)
        release.set()
        assert first.result()["current_version"]["status"] == "draft"
    assert len(models.calls) == 1
    models.callback = None
    second = {
        "request_id": uid(),
        "message_id": message["id"],
        "consent": True,
        "expected_version_id": service.get(a)["current_version"]["id"],
    }
    with connect(service.settings) as db:
        service._claim(db, a, "parse", second)
        db.execute(
            "UPDATE demand_requests SET lease_until=? WHERE id=?",
            (time.time() - 1, second["request_id"]),
        )
    assert service.parse(a, second)["current_version"]["number"] == 2


def test_stale_confirm_ambiguity_and_missing_explicit_choice(setup):
    service, history, models = setup
    a = history.create()["id"]
    models.output["possible_new_intent"] = True
    draft, _ = parse(service, history, a)
    request = confirmation(draft["current_version"])
    with pytest.raises(AppError, match="INTENT_CLARIFICATION_REQUIRED"):
        service.confirm(a, request)
    request["continue_current_intent"] = True
    request["edits"]["alternatives_acceptable"] = None
    with pytest.raises(AppError, match="DEMAND_EDIT_INVALID"):
        service.confirm(a, request)
    request["edits"]["alternatives_acceptable"] = True
    confirmed = service.confirm(a, request)
    with pytest.raises(AppError, match="DEMAND_VERSION_CONFLICT"):
        service.confirm(a, {**request, "request_id": uid()})
    history.add_message(a, "new message not parsed", uid())
    with pytest.raises(AppError, match="STALE_ANALYSIS"):
        service.confirm(a, confirmation(confirmed["current_version"]))


def test_ai_cannot_confirm_and_unknowns_remain_unknown(setup):
    service, history, models = setup
    a = history.create()["id"]
    models.output["required"][0]["confirmed"] = True
    with pytest.raises(AppError, match="DEMAND_STRUCTURE_INVALID"):
        parse(service, history, a)
    models.output["required"][0] = {"text": "unknown size", "source": "unknown", "evidence": ""}
    draft, _ = parse(service, history, a)
    confirmed = service.confirm(a, confirmation(draft["current_version"]))
    fact = confirmed["current_version"]["data"]["required"][0]
    assert fact["source"] == "unknown" and fact["confirmed"] is False
    assert confirmed["current_version"]["data"]["unknown"] == ["power consumption"]


def test_withdraw_is_terminal_and_duplicate_is_exact(setup):
    service, history, models = setup
    a = history.create()["id"]
    draft, _ = parse(service, history, a)
    confirmed = service.confirm(a, confirmation(draft["current_version"]))
    body = {
        "request_id": uid(),
        "expected_version_id": confirmed["current_version"]["id"],
        "confirm": True,
        "reason": "synthetic withdrawal",
    }
    one = service.withdraw(a, body)
    assert one["demand"]["status"] == "withdrawn"
    assert service.withdraw(a, body)["duplicate"]
    assert service.export(a, True)["packets"][-1]["message_type"] == "intent.withdraw"
    with pytest.raises(AppError, match="DEMAND_WITHDRAWN"):
        parse(service, history, a, expected=confirmed["current_version"]["id"])
    with pytest.raises(AppError, match="DEMAND_WITHDRAWN"):
        service.confirm(a, confirmation(confirmed["current_version"]))


def test_export_and_cascade_delete_include_versions_without_model_secrets(setup):
    service, history, models = setup
    a = history.create()["id"]
    draft, _ = parse(service, history, a)
    service.confirm(a, confirmation(draft["current_version"]))
    with pytest.raises(AppError, match="PRIVATE_EXPORT_CONSENT_REQUIRED"):
        service.export(a, False)
    export = history.export(a)
    assert export["schema"] == "demand-search.conversations.export/2"
    demand = export["conversations"][0]["demands"][0]
    assert len(demand["versions"]) == 2 and len(demand["packet_utf8"]) == 1
    assert "encrypted_secret" not in json.dumps(export)
    history.delete(a)
    with connect(service.settings) as db:
        for table in ("demands", "demand_versions", "demand_packets", "demand_requests"):
            assert db.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0


def test_independent_process_can_reopen_versions_and_exact_packets(setup):
    service, history, models = setup
    a = history.create()["id"]
    draft, _ = parse(service, history, a)
    service.confirm(a, confirmation(draft["current_version"]))
    expected = service.export(a, True)
    code = (
        "import json,sys; from pathlib import Path;"
        "from demand_search.config import Settings;"
        "from demand_search.demand_service import DemandService;"
        "service=DemandService(Settings(data_dir=Path(sys.argv[1])),None);"
        "print(json.dumps(service.export(sys.argv[2],True)))"
    )
    value = subprocess.check_output(
        [sys.executable, "-c", code, str(service.settings.data_dir), a],
        env={**os.environ, "PYTHONPATH": str(ROOT / "apps/server/src")},
        text=True,
    )
    assert json.loads(value) == expected


def test_http_routes_enforce_request_shape_and_preserve_original(setup):
    service, history, models = setup
    app = FastAPI()
    app.include_router(create_demand_router(service))

    @app.exception_handler(AppError)
    async def error(_request, exc):
        return JSONResponse({"error": {"code": exc.code}}, status_code=exc.status_code)

    a = history.create()["id"]
    message = history.add_message(a, "quiet 1500", uid())["message"]
    base = f"/api/v1/conversations/{a}/demand"
    with TestClient(app) as client:
        assert client.get(base).json()["demand"] is None
        request = {
            "request_id": uid(),
            "message_id": message["id"],
            "consent": True,
            "expected_version_id": None,
        }
        assert (
            client.post(base + "/parse", json={**request, "original_text": "forged"}).status_code
            == 422
        )
        draft = client.post(base + "/parse", json=request).json()
        confirmed = client.post(base + "/confirm", json=confirmation(draft["current_version"]))
        assert confirmed.status_code == 200
        assert client.post(base + "/export", json={"acknowledge_private_export": True}).json()[
            "packets"
        ]


def test_version_limit_rolls_back_confirmation_and_rejects_nonfinite_budget(setup, monkeypatch):
    from demand_search import demand_service

    service, history, models = setup
    a = history.create()["id"]
    draft, _ = parse(service, history, a)
    request = confirmation(draft["current_version"])
    request["edits"]["budget_ceiling"]["amount"] = float("nan")
    with pytest.raises(AppError, match="DEMAND_REQUEST_INVALID"):
        service.confirm(a, request)
    assert len(service.get(a)["versions"]) == 1
    confirmed = service.confirm(a, confirmation(draft["current_version"]))
    monkeypatch.setattr(demand_service, "MAX_VERSIONS", 2)
    with pytest.raises(AppError, match="DEMAND_LIMIT_REACHED"):
        service.confirm(a, confirmation(confirmed["current_version"]))
    assert service.get(a)["current_version"]["id"] == confirmed["current_version"]["id"]
    assert len(service.export(a, True)["packets"]) == 1

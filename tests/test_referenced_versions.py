"""Persisted historical discussion references; isolated synthetic data, never live AI."""

import copy
import json

import pytest
from demand_search.ai_demand import parse_demand, prepare_context
from demand_search.demand_routes import create_demand_router
from demand_search.demand_service import DemandService
from demand_search.errors import AppError
from demand_search.history_routes import create_history_router
from demand_search.history_service import HistoryService
from demand_search.storage import connect
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from test_ai_demand import client_for, config
from test_collaboration import configure, proposal, request
from test_demands import confirmation, uid
from test_demands import setup as imported_setup

demand_setup = imported_setup


@pytest.fixture
def setup(demand_setup):
    return demand_setup


def snapshots(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    old_plan = proposal()
    old_plan["collaboration"]["options"][0]["summary"] = "SYNTHETIC_OLD_PLAN_DETAIL"
    configure(models, old_plan)
    first = service.parse(
        conversation, request(history, conversation, "synthetic initial goal"), collaborative=True
    )["current_version"]
    approved = service.confirm(conversation, confirmation(first))["confirmed_version"]
    current_plan = proposal()
    current_plan["collaboration"]["options"][0]["summary"] = "SYNTHETIC_CURRENT_PLAN_DETAIL"
    configure(models, current_plan)
    current = service.parse(
        conversation,
        request(history, conversation, "synthetic later change", approved["id"]),
        collaborative=True,
    )["current_version"]
    return conversation, first, approved, current


def analysis_request(message, expected):
    return {
        "message_id": message["id"],
        "expected_version_id": expected,
        "request_id": uid(),
        "consent": True,
    }


def router_client(service, history):
    app = FastAPI()
    app.include_router(create_history_router(history))
    app.include_router(create_demand_router(service))

    @app.exception_handler(AppError)
    async def app_error(_request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status_code
        )

    return TestClient(app)


def test_reference_survives_restart_retry_and_appends_from_current_version(setup):
    service, history, models = setup
    conversation, first, approved, current = snapshots(setup)
    original = "  Discuss that earlier direction, without adopting it.\nKeep this wording. "
    sent = history.add_message(conversation, original, uid(), reference_version_id=first["id"])[
        "message"
    ]
    expected_reference = {key: first[key] for key in ("id", "number", "status")}
    assert sent["metadata"] == {"reference_version": expected_reference}
    assert sent["content"] == original
    frozen_packets = service.export(conversation, True)["packet_utf8"]

    restored_history = HistoryService(history.settings)
    restored_service = DemandService(service.settings, models)
    assert restored_history.get(conversation)["messages"][-1] == sent
    body = analysis_request(sent, current["id"])
    configure(models, proposal())
    output = restored_service.parse(conversation, body, collaborative=True)
    context = models.calls[-1][1]
    assert context["referenced_version"] == {**expected_reference, "data": first["data"]}
    assert context["current_draft"] == current["data"]
    assert context["confirmed_demand"] == approved["data"]
    assert output["current_version"]["parent_version_id"] == current["id"]
    assert output["current_version"]["original_text"] == original
    assert output["current_version"]["status"] == "draft"
    assert not output["current_version"]["data"]["solution_confirmed"]
    assert output["current_version"]["data"]["solution_selection"] is None
    assert output["confirmed_version"] == approved
    assert next(v for v in output["versions"] if v["id"] == first["id"]) == first
    assert restored_service.export(conversation, True)["packet_utf8"] == frozen_packets

    called = len(models.calls)
    retry = DemandService(service.settings, models).parse(conversation, body, collaborative=True)
    assert retry["duplicate"] is True
    assert retry["result_version_id"] == output["result_version_id"]
    assert len(models.calls) == called
    exported = restored_history.export(conversation)["conversations"][0]["messages"][-1]
    assert exported["metadata"] == sent["metadata"] and exported["content"] == original


@pytest.mark.parametrize("kind", ["missing", "other_conversation", "other_owner", "malformed"])
def test_unowned_and_missing_references_reject_without_inserting_message(setup, kind):
    service, history, models = setup
    conversation, first, _approved, _current = snapshots(setup)
    target, reference = conversation, first["id"]
    code = "REFERENCE_VERSION_NOT_FOUND"
    if kind == "missing":
        reference = uid()
    elif kind == "other_conversation":
        target = history.create()["id"]
    elif kind == "other_owner":
        with connect(service.settings) as db:
            db.execute(
                "UPDATE demands SET owner_id='synthetic-foreign-owner' WHERE conversation_id=?",
                (conversation,),
            )
    else:
        reference, code = "not-a-version", "INVALID_INPUT"
    before = history.get(target)
    with pytest.raises(AppError, match=code):
        history.add_message(target, "synthetic feedback", uid(), reference_version_id=reference)
    assert history.get(target) == before


@pytest.mark.parametrize("initial_reference", [True, False])
def test_message_idempotency_includes_reference_and_keeps_legacy_default(setup, initial_reference):
    _service, history, _models = setup
    conversation, first, _approved, current = snapshots(setup)
    identity = uid()
    ref = first["id"] if initial_reference else None
    sent = history.add_message(
        conversation, "synthetic identical text", identity, reference_version_id=ref
    )
    duplicate = HistoryService(history.settings).add_message(
        conversation, "synthetic identical text", identity, reference_version_id=ref
    )
    assert duplicate["duplicate"] and duplicate["message"] == sent["message"]
    for changed_ref in [None, current["id"]] if initial_reference else [first["id"]]:
        with pytest.raises(AppError, match="MESSAGE_ID_CONFLICT"):
            history.add_message(
                conversation,
                "synthetic identical text",
                identity,
                reference_version_id=changed_ref,
            )
    if not initial_reference:
        assert sent["message"]["metadata"] == {}
        assert history.add_message(conversation, "synthetic identical text", identity)["duplicate"]


def test_http_accepts_only_reference_identity_and_stream_restores_its_snapshot(setup):
    service, history, models = setup
    conversation, first, _approved, current = snapshots(setup)
    configure(models, proposal())
    url = "/api/v1/conversations/" + conversation
    packet = {
        "content": "synthetic discuss old plan",
        "client_message_id": uid(),
        "reference_version_id": first["id"],
    }
    with router_client(service, history) as client:
        forged = {**packet, "metadata": {"reference_version": {"status": "confirmed"}}}
        assert client.post(url + "/messages", json=forged).status_code == 422
        assert (
            client.post(
                url + "/messages", json={**packet, "reference_version_id": "bad-id"}
            ).status_code
            == 422
        )
        response = client.post(url + "/messages", json=packet)
        assert response.status_code == 200
        message = response.json()["message"]
        assert message["metadata"]["reference_version"]["status"] == "draft"
        body = analysis_request(message, current["id"])
        assert (
            client.post(
                url + "/demand/collaborate",
                json={**body, "reference_version_id": current["id"]},
            ).status_code
            == 422
        )
        result = client.post(url + "/demand/collaborate", json=body)
    events = [json.loads(line) for line in result.text.splitlines()]
    assert events[0]["type"] == "start" and events[-1]["type"] == "complete"
    assert models.calls[-1][1]["referenced_version"]["data"] == first["data"]


def test_failed_analysis_can_retry_from_persisted_reference_after_restart(setup):
    service, history, models = setup
    conversation, first, approved, current = snapshots(setup)
    message = history.add_message(
        conversation, "synthetic retry feedback", uid(), reference_version_id=first["id"]
    )["message"]
    body = analysis_request(message, current["id"])
    contexts = []

    def fail(_text, context, *_args, **_kwargs):
        contexts.append(copy.deepcopy(context))
        raise AppError("PROVIDER_TIMEOUT", "synthetic failure", 504)

    models.parse_demand = fail
    with pytest.raises(AppError, match="PROVIDER_TIMEOUT"):
        service.parse(conversation, body, collaborative=True)
    unchanged = service.get(conversation)
    assert unchanged["current_version"] == current
    assert unchanged["confirmed_version"] == approved
    configure(models, proposal())
    restarted = DemandService(service.settings, models)
    output = restarted.parse(conversation, body, collaborative=True)
    assert models.calls[-1][1] == contexts[0]
    assert output["current_version"]["parent_version_id"] == current["id"]


def test_reference_does_not_bypass_current_version_conflict_or_restore_confirmed_state(setup):
    service, history, models = setup
    conversation, first, approved, current = snapshots(setup)
    message = history.add_message(
        conversation, "synthetic request", uid(), reference_version_id=approved["id"]
    )["message"]
    calls = len(models.calls)
    with pytest.raises(AppError, match="DEMAND_VERSION_CONFLICT"):
        service.parse(conversation, analysis_request(message, first["id"]), collaborative=True)
    assert len(models.calls) == calls
    output = service.parse(
        conversation, analysis_request(message, current["id"]), collaborative=True
    )
    assert models.calls[-1][1]["referenced_version"]["status"] == "confirmed"
    assert output["current_version"]["status"] == "draft"
    assert output["confirmed_version"] == approved


def test_reference_is_revalidated_on_parse_without_trusting_persisted_labels(setup):
    service, history, models = setup
    conversation, first, _approved, current = snapshots(setup)
    message = history.add_message(
        conversation, "synthetic referenced feedback", uid(), reference_version_id=first["id"]
    )["message"]
    with connect(service.settings) as db:
        db.execute(
            "UPDATE demands SET owner_id='synthetic-other-owner' WHERE conversation_id=?",
            (conversation,),
        )
    calls = len(models.calls)
    with pytest.raises(AppError, match="REFERENCE_VERSION_NOT_FOUND"):
        service.parse(conversation, analysis_request(message, None), collaborative=True)
    assert len(models.calls) == calls


def test_historical_plan_never_becomes_user_evidence_or_confirmed_budget():
    value = proposal()
    marker = "SYNTHETIC_ONLY_OLD_PLAN"
    evidence = marker + " 9000 CNY"
    value["required"] = [{"text": marker, "source": "user_explicit", "evidence": evidence}]
    value["budget_ceiling"] = {
        "amount": 9000.0,
        "currency": "CNY",
        "source": "user_explicit",
        "evidence": evidence,
    }
    context = {
        "referenced_version": {
            "id": uid(),
            "number": 1,
            "status": "draft",
            "data": {"assistant_reply": evidence, "solution_confirmed": False},
        },
        "recent_messages": [{"content": "synthetic previous user words"}],
    }
    serialized, user_evidence = prepare_context("discuss that plan", context)
    assert evidence in serialized and marker not in user_evidence
    captured = []
    result = parse_demand(
        client_for(value, captured),
        config(),
        "synthetic-unusable-key",
        "discuss that plan",
        context,
        collaborative=True,
    )
    assert result["parsed"]["required"][0]["source"] == "model_inferred"
    assert result["parsed"]["budget_ceiling"]["source"] == "model_inferred"
    assert result["parsed"]["user_confirmed"] is False
    assert result["prompt_version"] == "demand-search-collaboration/2"
    instructions = captured[0]["input"][0]["content"]
    assert "not adoption, confirmation, or rollback" in instructions
    assert "historical interpretations, never new evidence" in instructions


def test_oversized_full_snapshot_rejected_before_model_and_not_silently_truncated(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    oversized = proposal()
    oversized["assistant_reply"] = "s" * 12000
    for option in oversized["collaboration"]["options"]:
        option["summary"] = "x" * 1600
        option["steps"] = ["step" * 150] * 12
        option["tradeoffs"] = ["trade" * 120] * 8
    configure(models, oversized)
    first = service.parse(
        conversation, request(history, conversation, "synthetic initial"), collaborative=True
    )["current_version"]
    assert len(json.dumps(first["data"], ensure_ascii=False)) > 32000
    message = history.add_message(
        conversation, "discuss the previous proposal", uid(), reference_version_id=first["id"]
    )["message"]
    calls = len(models.calls)
    with pytest.raises(AppError, match="CONTEXT_TOO_LARGE") as error:
        service.parse(conversation, analysis_request(message, first["id"]), collaborative=True)
    assert "32000" in error.value.message
    assert len(models.calls) == calls
    assert service.get(conversation)["current_version"] == first
    assert history.get(conversation)["messages"][-1] == message


def test_no_reference_preserves_context_shape_and_original_message_metadata(setup):
    service, history, models = setup
    conversation, _first, _approved, current = snapshots(setup)
    message = history.add_message(conversation, "synthetic no reference", uid())["message"]
    assert message["metadata"] == {}
    service.parse(conversation, analysis_request(message, current["id"]), collaborative=True)
    assert set(models.calls[-1][1]) == {"confirmed_demand", "current_draft", "recent_messages"}
    encoded, _evidence = prepare_context("test", models.calls[-1][1])
    assert "referenced_version" not in json.loads(encoded)

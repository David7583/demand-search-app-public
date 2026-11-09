"""Synthetic strategy contracts and real local version/stream transactions; no paid AI."""

import copy
import json
import threading

import pytest
from demand_search.ai_demand import CollaborativeDemand, parse_demand
from demand_search.collaboration import Collaboration, ReplyDecoder, validate_helpfulness
from demand_search.demand_routes import create_demand_router
from demand_search.demand_service import validate_data
from demand_search.errors import AppError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_demands import confirmation, data, uid
from test_demands import setup as imported_setup

demand_setup = imported_setup


@pytest.fixture
def setup(demand_setup):
    return demand_setup


def proposal(strategy="plan_first", task_type="planning"):
    value = data()
    value["items"] = []
    value["budget_ceiling"] = None
    value["clarification_questions"] = (
        [] if strategy == "execute_first" else ["哪条方向值得优先调整？"]
    )
    value["assistant_reply"] = "先给可讨论方案，再根据反馈改进。预算仅为粗略示例，非报价。"
    value["collaboration"] = {
        "strategy": strategy,
        "rationale": "目标已有方向，先提供可行动的帮助，不等待所有字段齐全。",
        "task_type": task_type,
        "assumptions": ["暂按可逆、小规模试用规划，尚未确认。"],
        "options": [
            {
                "option_id": "gentle",
                "title": "低成本渐进试用",
                "summary": "先整理现有条件并试用一个局部，再决定是否扩大投入。",
                "steps": ["记录现状", "做一个可撤回的小规模试验"],
                "tradeoffs": ["见效较慢，但便于撤回"],
                "budget_estimate": {
                    "low": 1000.0,
                    "high": 3000.0,
                    "currency": "CNY",
                    "basis": "仅供比较两种投入规模的假设",
                    "note": "未经供应商核验的粗略示例，非报价",
                },
            },
            {
                "option_id": "focused",
                "title": "集中解决主要问题",
                "summary": "先识别一个最重要的问题，集中有限资源验证。",
                "steps": ["确定成功标准"],
                "tradeoffs": ["暂不处理次要问题"],
                "budget_estimate": None,
            },
        ],
        "next_steps": ["在工作区比较方向并给出反馈"],
        "limitations": ["没有查询真实商品、供应商或报价；关键条件尚未核实。"],
        "needs_verification": strategy == "verify_first",
    }
    return value


def configure(models, output, on_call=None):
    def response(text, context, consent, config_id=None, *, on_delta=None, collaborative=False):
        assert collaborative and consent
        models.calls.append((text, copy.deepcopy(context)))
        if on_delta:
            on_delta(output["assistant_reply"][:6])
            if on_call:
                on_call()
            on_delta(output["assistant_reply"][6:])
        return {
            "parsed": copy.deepcopy(output),
            "actual_model": "synthetic-adaptive",
            "provider": "custom",
            "prompt_version": "synthetic-collaboration/1",
        }

    models.parse_demand = response


def request(history, conversation, text, expected=None):
    message = history.add_message(conversation, text, uid())["message"]
    return {
        "request_id": uid(),
        "message_id": message["id"],
        "expected_version_id": expected,
        "consent": True,
    }


@pytest.mark.parametrize(
    "text,strategy,task_type",
    [
        ("我想改善家里居住体验，先给一个可以讨论的装修规划。", "plan_first", "planning"),
        ("我想做个有用的产品，但还没想好解决谁的问题。", "explore_first", "exploration"),
        ("帮我整理3000元以内的办公椅搜索关键词，不需要再提问。", "execute_first", "shopping"),
    ],
)
def test_representative_helpful_first_contracts(setup, text, strategy, task_type):
    service, history, models = setup
    conversation = history.create()["id"]
    configure(models, proposal(strategy, task_type))
    output = service.parse(conversation, request(history, conversation, text), collaborative=True)
    version = output["current_version"]
    assert version["original_text"] == text
    assert version["status"] == "draft" and output["confirmed_version"] is None
    assert version["data"]["collaboration"]["strategy"] == strategy
    assert version["data"]["assistant_reply"]
    assert version["data"]["budget_ceiling"] is None
    assert version["data"]["solution_confirmed"] is False
    assert service.export(conversation, True)["packets"] == []


def test_same_conversation_switches_strategy_and_preserves_confirmation_and_feedback(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    old = None
    frozen = None
    for index, (strategy, text) in enumerate(
        [
            ("plan_first", "先给我装修改善方案"),
            ("explore_first", "我还没想清楚，也可以看看非装修的改善方向"),
            ("execute_first", "保留已有条件，帮我整理台灯搜索入口"),
            ("verify_first", "我现在想拆承重墙，请直接告诉我操作步骤"),
        ]
    ):
        value = proposal(strategy, "shopping" if index == 2 else "planning")
        if strategy == "verify_first":
            value["assistant_reply"] = "先不要拆改，需要专业核实结构条件；可以先整理图纸。"
            value["clarification_questions"] = ["有具备资质人员出具的结构核实结果吗？"]
            value["collaboration"]["next_steps"] = ["暂停拆改，整理图纸咨询专业人员"]
        configure(models, value)
        output = service.parse(
            conversation,
            request(history, conversation, text, old),
            collaborative=True,
        )
        assert output["current_version"]["parent_version_id"] == old
        if index == 0:
            confirmed = service.confirm(conversation, confirmation(output["current_version"]))
            frozen = copy.deepcopy(confirmed["confirmed_version"])
            old = frozen["id"]
            assert frozen["data"]["solution_confirmed"] is False
        else:
            assert output["confirmed_version"] == frozen
            assert (
                models.calls[-1][1]["confirmed_demand"]["desired_outcome"]
                == frozen["data"]["desired_outcome"]
            )
            old = output["current_version"]["id"]
    assert len(service.get(conversation)["versions"]) == 5


def test_helpfulness_rejects_questionnaire_and_unverified_execution():
    value = proposal()
    value["collaboration"]["options"] = []
    with pytest.raises(AppError, match="AI_COLLABORATION_INVALID"):
        validate_helpfulness(value)
    value = proposal("explore_first")
    value["collaboration"]["options"] = value["collaboration"]["options"][:1]
    with pytest.raises(AppError, match="AI_COLLABORATION_INVALID"):
        validate_helpfulness(value)
    value = proposal("execute_first")
    value["clarification_questions"] = ["无关问题"]
    with pytest.raises(AppError, match="AI_COLLABORATION_INVALID"):
        validate_helpfulness(value)
    value = proposal("execute_first")
    value["collaboration"]["needs_verification"] = True
    with pytest.raises(ValidationError):
        Collaboration.model_validate(value["collaboration"])
    value = proposal("verify_first")
    value["clarification_questions"] = []
    with pytest.raises(AppError, match="AI_COLLABORATION_INVALID"):
        validate_helpfulness(value)


def test_solution_adoption_is_explicit_separate_and_not_fact_verification(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    configure(models, proposal())
    output = service.parse(
        conversation, request(history, conversation, "先给方向"), collaborative=True
    )
    body = confirmation(output["current_version"])
    body.update(selected_option_id="gentle", confirm_solution=True)
    confirmed = service.confirm(conversation, body)["confirmed_version"]
    assert confirmed["data"]["solution_confirmed"] is True
    assert confirmed["data"]["solution_selection"] == {
        "option_id": "gentle",
        "status": "user_selected",
    }
    assert confirmed["data"]["budget_ceiling"] is None
    assert "尚未确认" in confirmed["data"]["collaboration"]["assumptions"][0]
    bad = confirmation(confirmed)
    bad.update(selected_option_id="missing", confirm_solution=True)
    with pytest.raises(AppError, match="SOLUTION_OPTION_UNKNOWN"):
        service.confirm(conversation, bad)
    assert service.get(conversation)["confirmed_version"] == confirmed
    configure(models, proposal())
    revised = service.parse(
        conversation,
        request(history, conversation, "换个方向，原选择暂不采用", confirmed["id"]),
        collaborative=True,
    )
    assert revised["current_version"]["data"]["solution_confirmed"] is False
    assert revised["current_version"]["data"]["solution_selection"] is None


def test_critical_plan_cannot_be_adopted_until_verified(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    configure(models, proposal("verify_first"))
    output = service.parse(
        conversation, request(history, conversation, "高风险条件未知"), collaborative=True
    )
    body = confirmation(output["current_version"])
    body.update(confirm_solution=True, selected_option_id="gentle")
    with pytest.raises(AppError, match="SOLUTION_REQUIRES_VERIFICATION"):
        service.confirm(conversation, body)
    assert service.get(conversation)["confirmed_version"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("solution_confirmed", True),
        ("solution_selection", {"option_id": "gentle", "status": "user_selected"}),
    ],
)
def test_ai_cannot_adopt_solution(field, value):
    output = proposal()
    output[field] = value
    with pytest.raises(AppError, match="DEMAND_STRUCTURE_INVALID"):
        validate_data(output, ai=True)


def test_stream_commits_only_after_completion_and_retries_without_calling_model(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    configure(
        models,
        proposal(),
        on_call=lambda: (
            service.get(conversation)["current_version"] is None
            or pytest.fail("Partial output was committed")
        ),
    )
    body = request(history, conversation, "先讨论家装方案")
    app = FastAPI()
    app.include_router(create_demand_router(service))
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/conversations/{conversation}/demand/collaborate", json=body
        )
        events = [json.loads(line) for line in response.text.splitlines()]
        assert [event["type"] for event in events] == ["start", "delta", "delta", "complete"]
        view = events[-1]["view"]
        assert view["current_version"]["status"] == "draft"
        again = client.post(f"/api/v1/conversations/{conversation}/demand/collaborate", json=body)
        retry = [json.loads(line) for line in again.text.splitlines()]
        assert [event["type"] for event in retry] == ["start", "complete"]
        assert retry[-1]["view"]["duplicate"] is True
    assert len(models.calls) == 1


def test_late_and_cancelled_streams_cannot_mutate_saved_demand(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    configure(models, proposal())
    body = request(history, conversation, "先给方案")
    stopped = threading.Event()

    def cancel_check():
        if stopped.is_set():
            raise AppError("STREAM_CANCELLED", "synthetic cancel", 409)

    with pytest.raises(AppError, match="STREAM_CANCELLED"):
        service.parse(
            conversation,
            body,
            collaborative=True,
            on_delta=lambda _: stopped.set(),
            cancel_check=cancel_check,
        )
    assert service.get(conversation)["versions"] == []
    configure(
        models, proposal(), on_call=lambda: history.add_message(conversation, "补充新条件", uid())
    )
    with pytest.raises(AppError, match="STALE_ANALYSIS"):
        service.parse(conversation, body, collaborative=True, on_delta=lambda _: None)
    assert service.get(conversation)["versions"] == []


def test_stream_error_is_sanitized_and_preserves_old_versions(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    body = request(history, conversation, "不完整的建议")
    value = proposal()
    value["assistant_reply"] = ""
    configure(models, value)
    app = FastAPI()
    app.include_router(create_demand_router(service))
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/conversations/{conversation}/demand/collaborate", json=body
        )
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["type"] == "error"
    assert events[-1]["error"]["code"] == "AI_COLLABORATION_INVALID"
    assert not any(event["type"] == "complete" for event in events)
    assert service.get(conversation)["versions"] == []


def test_reply_decoder_handles_every_character_boundary_without_leaking_other_fields():
    reply = '方案😀：先试用。\\n"\n再讨论'
    raw = json.dumps(
        {
            "ignored": {"assistant_reply": "NESTED_MUST_NOT_SHOW"},
            "assistant_reply": reply,
            "private": "OTHER_FIELD",
        },
        ensure_ascii=True,
    )
    pieces = []
    decoder = ReplyDecoder(pieces.append)
    for character in raw:
        decoder.feed(character)
    assert "".join(pieces) == reply
    assert "OTHER_FIELD" not in "".join(pieces) and "NESTED" not in "".join(pieces)
    with pytest.raises(AppError, match="AI_RESPONSE_TOO_LARGE"):
        decoder.feed("x" * (512 * 1024))


def test_new_prompt_and_response_contract_are_distinct_from_legacy_parser():
    class Client:
        captured = None

        def parse(self, config, key, text, **kwargs):
            self.captured = kwargs
            value = proposal()
            validated = kwargs["output_model"].model_validate(value).model_dump()
            raw = json.dumps(
                {"assistant_reply": validated["assistant_reply"], **validated}, ensure_ascii=True
            )
            for char in raw:
                kwargs["on_delta"](char)
            return {"parsed": validated, "actual_model": "synthetic"}

    client, pieces = Client(), []
    result = parse_demand(
        client,
        {},
        "synthetic-secret-never-used",
        "我想改善家居",
        {},
        on_delta=pieces.append,
        collaborative=True,
    )
    assert client.captured["output_model"] is CollaborativeDemand
    assert next(iter(CollaborativeDemand.model_fields)) == "assistant_reply"
    assert "not a questionnaire" in client.captured["instruction_suffix"]
    assert "No product or affiliate APIs" in client.captured["instruction_suffix"]
    assert "".join(pieces) == result["parsed"]["assistant_reply"]
    assert result["prompt_version"] == "demand-search-collaboration/2"


def test_route_disconnect_cancels_worker_before_persistence(setup):
    import asyncio
    from uuid import UUID

    from demand_search.demand_models import ParseRequest
    from demand_search.storage import connect

    service, history, models = setup
    conversation = history.create()["id"]
    release = threading.Event()
    body = request(history, conversation, "先给可讨论方案")
    configure(models, proposal(), on_call=lambda: release.wait(timeout=5))
    router = create_demand_router(service)
    endpoint = next(
        route.endpoint for route in router.routes if route.path.endswith("/collaborate")
    )

    async def exercise():
        response = await endpoint(UUID(conversation), ParseRequest.model_validate(body))
        iterator = response.body_iterator
        assert json.loads(await anext(iterator))["type"] == "start"
        assert json.loads(await anext(iterator))["type"] == "delta"
        await iterator.aclose()
        release.set()
        for _ in range(100):
            with connect(service.settings) as db:
                state = db.execute(
                    "SELECT state FROM demand_requests WHERE id=?", (body["request_id"],)
                ).fetchone()
            if state and state["state"] == "failed":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("Cancelled worker did not release its request")
        assert service.get(conversation)["versions"] == []

    try:
        asyncio.run(exercise())
    finally:
        release.set()


def test_collaboration_idempotency_scope_and_parallel_claim(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    body = request(history, conversation, "先给方案")
    value = proposal()
    blocked = []

    def parallel():
        with pytest.raises(AppError, match="REQUEST_IN_PROGRESS"):
            service.parse(conversation, body, collaborative=True)
        blocked.append(True)

    configure(models, value, on_call=parallel)
    output = service.parse(conversation, body, collaborative=True, on_delta=lambda _: None)
    assert blocked == [True]
    assert output["current_version"]["number"] == 1
    with pytest.raises(AppError, match="REQUEST_ID_CONFLICT"):
        service.parse(conversation, body)  # Same ID cannot switch to legacy operation.
    other = history.create()["id"]
    with pytest.raises(AppError, match="REQUEST_ID_CONFLICT"):
        service.parse(other, body, collaborative=True)
    assert len(models.calls) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"low": 4000.0, "high": 3000.0},
        {"low": -1.0},
        {"high": float("nan")},
        {"note": "   "},
    ],
)
def test_estimates_remain_bounded_explicit_uncertainty_not_quotes(change):
    plan = proposal()["collaboration"]
    plan["options"][0]["budget_estimate"].update(change)
    with pytest.raises(ValidationError):
        Collaboration.model_validate(plan)


def test_legacy_snapshot_stays_byte_exact_after_collaborative_revision(setup):
    from demand_search.storage import connect

    service, history, models = setup
    conversation = history.create()["id"]
    body = request(history, conversation, "最初的合成原话")
    first = service.parse(conversation, body)
    old = first["current_version"]["id"]
    with connect(service.settings) as db:
        before = db.execute("SELECT data_json FROM demand_versions WHERE id=?", (old,)).fetchone()[
            0
        ]
    assert "collaboration" in before  # A new legacy-parser snapshot has compatible defaults.
    # Emulate an existing pre-upgrade stored snapshot with no new keys, without rewriting
    # it through application code; afterwards the collaboration path must leave it alone.
    import json

    prior = json.loads(before)
    for field in ("assistant_reply", "collaboration", "solution_selection", "solution_confirmed"):
        prior.pop(field)
    exact = json.dumps(prior, ensure_ascii=True, separators=(", ", ": "))
    with connect(service.settings) as db:
        db.execute("UPDATE demand_versions SET data_json=? WHERE id=?", (exact, old))
    configure(models, proposal())
    service.parse(
        conversation,
        request(history, conversation, "基于旧记录给我一份方案", old),
        collaborative=True,
    )
    with connect(service.settings) as db:
        after = db.execute("SELECT data_json FROM demand_versions WHERE id=?", (old,)).fetchone()[0]
    assert after == exact

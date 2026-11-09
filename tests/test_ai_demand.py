"""S2 model structure tests; network responses and credentials are synthetic."""

import json

import pytest
from demand_search.ai_demand import AiDemand, parse_demand, prepare_context
from demand_search.errors import AppError
from demand_search.providers import ProviderClient


def data():
    return {
        "desired_outcome": "办公椅",
        "required": [{"text": "久坐", "source": "user_explicit", "evidence": "适合久坐"}],
        "preferred": [],
        "unknown": ["尺寸"],
        "budget_ceiling": {
            "amount": 3000,
            "currency": "CNY",
            "source": "user_explicit",
            "evidence": "预算3000 CNY",
        },
        "readiness": "need",
        "alternatives_acceptable": None,
        "clarification_questions": ["座位宽度有要求吗？"],
        "possible_new_intent": False,
        "items": [],
    }


def config():
    return {
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_mode": "responses",
        "model": "synthetic-model",
    }


def client_for(value, captured):
    client = ProviderClient()

    def response(*args):
        captured.append(args[-1])
        return {
            "model": "synthetic-actual",
            "status": "completed",
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": json.dumps(value)}]}
            ],
        }

    client.request_json = response
    return client


def test_context_is_bounded_and_prior_interpretation_is_not_user_evidence():
    captured = []
    value = data()
    value["required"] = [{"text": "imagined", "source": "user_explicit", "evidence": "imagined"}]
    context = {
        "confirmed_demand": {"desired_outcome": "imagined"},
        "recent_messages": [{"content": "适合久坐", "id": "synthetic"}],
    }
    result = parse_demand(
        client_for(value, captured), config(), "synthetic-key", "预算3000 CNY", context
    )
    assert result["parsed"]["original_text"] == "预算3000 CNY"
    assert result["parsed"]["required"][0]["source"] == "model_inferred"
    assert result["parsed"]["budget_ceiling"]["source"] == "user_explicit"
    assert result["parsed"]["user_confirmed"] is False
    assert result["prompt_version"] == "demand-search-s2.1/1"
    body = captured[0]
    assert body["store"] is False and "tools" not in body
    schema = body["text"]["format"]["schema"]
    assert set(schema["required"]) == set(schema["properties"])
    assert AiDemand.model_validate(value).alternatives_acceptable is None


def test_context_limit_and_key_leak_fail_before_network():
    with pytest.raises(AppError, match="CONTEXT_TOO_LARGE"):
        prepare_context("hello", {"recent_messages": [{"content": "x" * 6001}]})
    with pytest.raises(AppError, match="CONTEXT_TOO_LARGE"):
        prepare_context("hello", {"confirmed_demand": {"text": "x" * 32000}})
    captured = []
    with pytest.raises(AppError, match="KEY_IN_TEST_TEXT"):
        parse_demand(
            client_for(data(), captured),
            config(),
            "synthetic-key",
            "hello",
            {"recent_messages": [{"content": "synthetic-key"}]},
        )
    assert captured == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("user_confirmed", True),
        ("clarification_questions", ["a", "b", "c"]),
        (
            "budget_ceiling",
            {"amount": float("nan"), "currency": "CNY", "source": "unknown", "evidence": ""},
        ),
        ("alternatives_acceptable", "yes"),
    ],
)
def test_ai_cannot_bypass_schema_or_confirm(field, value):
    result = data()
    result[field] = value
    with pytest.raises(AppError, match="AI_SCHEMA_INVALID"):
        parse_demand(client_for(result, []), config(), "synthetic-key", "预算3000 CNY", {})


def test_malicious_provider_key_echo_is_redacted():
    value = data()
    value["desired_outcome"] = "synthetic-key"
    result = parse_demand(client_for(value, []), config(), "synthetic-key", "预算3000 CNY", {})
    assert "synthetic-key" not in json.dumps(result)

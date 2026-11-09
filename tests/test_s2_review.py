"""Independent S2 security regressions using synthetic credentials and isolated test storage."""

import copy
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from demand_search.ai_demand import parse_demand
from demand_search.config import ROOT, Settings
from demand_search.demand_service import DemandService
from demand_search.errors import AppError
from demand_search.history_service import HistoryService
from demand_search.storage import connect, initialize


def demand_data():
    return {
        "desired_outcome": "Synthetic review need",
        "required": [],
        "preferred": [],
        "unknown": [],
        "budget_ceiling": None,
        "readiness": "exploring",
        "alternatives_acceptable": None,
        "clarification_questions": [],
        "possible_new_intent": False,
    }


class SpyProvider:
    def __init__(self):
        self.calls = []
        self.output = demand_data()

    def parse(self, config, key, text, **kwargs):
        self.calls.append(text)
        return {
            "actual_model": "synthetic-review-model",
            "parsed": {
                **copy.deepcopy(self.output),
                "original_text": kwargs.get("original_text", text),
                "user_confirmed": False,
            },
        }


@pytest.mark.parametrize("key", ['synthetic"quote-key', r"synthetic\slash-key"])
@pytest.mark.parametrize("location", ["current", "recent", "confirmed_field", "confirmed_key"])
def test_review_escaped_credentials_never_enter_model_context(key, location):
    provider = SpyProvider()
    text, context = "Synthetic input", {}
    if location == "current":
        text = "Pasted " + key
    elif location == "recent":
        context = {"recent_messages": [{"content": "Pasted " + key}]}
    elif location == "confirmed_field":
        context = {"confirmed_demand": {"required": [{"text": key}]}}
    else:
        context = {"confirmed_demand": {key: "synthetic"}}
    with pytest.raises(AppError, match="KEY_IN_TEST_TEXT"):
        parse_demand(provider, {}, key, text, context)
    assert provider.calls == []


@pytest.mark.parametrize(
    "amount,currency,evidence",
    [(3000, "USD", "budget"), (3000, "CNY", "1500 CNY"), (1500, "USD", "1500 CNY")],
)
def test_review_budget_values_must_be_supported_before_marked_user_explicit(
    amount, currency, evidence
):
    provider = SpyProvider()
    provider.output["budget_ceiling"] = {
        "amount": amount,
        "currency": currency,
        "source": "user_explicit",
        "evidence": evidence,
    }
    result = parse_demand(
        provider,
        {},
        "synthetic-review-key",
        "Synthetic budget 1500 CNY",
        {},
    )
    assert result["parsed"]["budget_ceiling"]["source"] == "model_inferred"


def test_review_replaced_lease_cannot_commit_a_late_first_response():
    folder = ROOT / "runtime" / ("test-s2-review-" + uuid4().hex)
    settings = Settings(data_dir=folder)
    initialize(settings)
    entered = [threading.Event(), threading.Event()]
    release = [threading.Event(), threading.Event()]
    call_lock = threading.Lock()

    class Models:
        count = 0

        def parse_demand(self, text, context, consent, config_id=None):
            with call_lock:
                position = self.count
                self.count += 1
            entered[position].set()
            assert release[position].wait(timeout=10)
            return {
                "actual_model": "synthetic-" + str(position),
                "provider": "custom",
                "parsed": {**demand_data(), "original_text": text, "user_confirmed": False},
            }

    models = Models()
    service, history = DemandService(settings, models), HistoryService(settings)
    conversation = history.create("Synthetic lease review")["id"]
    message = history.add_message(conversation, "Synthetic original", str(uuid4()))["message"]
    body = {
        "request_id": str(uuid4()),
        "message_id": message["id"],
        "expected_version_id": None,
        "consent": True,
    }
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(service.parse, conversation, body)
            try:
                assert entered[0].wait(timeout=5)
                with connect(settings) as db:
                    db.execute(
                        "UPDATE demand_requests SET lease_until=? WHERE id=?",
                        (time.time() - 1, body["request_id"]),
                    )
                second = pool.submit(service.parse, conversation, body)
                assert entered[1].wait(timeout=5)
                # The replacement is still in flight when the original call returns.
                release[0].set()
                with pytest.raises(AppError, match="REQUEST_REPLACED"):
                    first.result(timeout=5)
                assert service.get(conversation)["versions"] == []
                release[1].set()
                result = second.result(timeout=5)
                assert len(result["versions"]) == 1
                assert result["current_version"]["model"] == "synthetic-1"
                assert models.count == 2
            finally:
                for event in release:
                    event.set()
    finally:
        assert folder.resolve().is_relative_to((ROOT / "runtime").resolve())
        shutil.rmtree(folder)

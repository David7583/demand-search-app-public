"""Three bounded AI-context checks; synthetic provider responses and no real keys/network."""

import copy
import json
import shutil
import socket
from collections import Counter
from types import SimpleNamespace
from uuid import uuid4

import pytest
from demand_search import market_context
from demand_search.config import ROOT, Settings
from demand_search.model_service import ModelService
from demand_search.providers import ProviderClient
from demand_search.simulated_market import DATABASE_NAME, _read_store, initialize_market


def response_data(collaborative, claimed_evidence=""):
    value = {
        "items": [],
        "desired_outcome": "Discuss the synthetic catalog",
        "required": (
            [{"text": claimed_evidence, "source": "user_explicit", "evidence": claimed_evidence}]
            if claimed_evidence
            else []
        ),
        "preferred": [],
        "unknown": [],
        "budget_ceiling": None,
        "readiness": "exploring",
        "alternatives_acceptable": None,
        "clarification_questions": [],
        "possible_new_intent": False,
    }
    if collaborative:
        value.update(
            assistant_reply="The catalog overview is synthetic; no offers have been retrieved.",
            collaboration={
                "strategy": "execute_first",
                "rationale": "Catalog coverage can be discussed without confirming a demand.",
                "task_type": "general",
                "assumptions": [],
                "options": [],
                "next_steps": ["Choose a catalog category to discuss."],
                "limitations": [
                    "No product search, real supply check or quote has been performed."
                ],
                "needs_verification": False,
            },
        )
    return value


class CapturingProvider(ProviderClient):
    def __init__(self):
        self.requests = []
        self.evidence = []
        self.claimed_evidence = ""

    def parse(self, *args, **kwargs):
        self.evidence.append(kwargs["evidence_text"])
        return super().parse(*args, **kwargs)

    def request_json(self, _base, _provider, _key, _method, _path, body=None):
        self.requests.append(copy.deepcopy(body))
        collaborative = "assistant_reply" in body["text"]["format"]["schema"]["properties"]
        content = json.dumps(response_data(collaborative, self.claimed_evidence))
        return {
            "model": "synthetic-context-provider",
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": content}]}],
        }


@pytest.fixture
def setup(monkeypatch):
    folder = ROOT / "runtime" / ("test-market-ai-context-" + uuid4().hex)
    settings = Settings(data_dir=folder)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Market AI-context tests must not make network calls")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    client = CapturingProvider()
    vault = SimpleNamespace(unseal=lambda *_args: "SYNTHETIC_CONTEXT_TEST_TOKEN_0000")
    service = ModelService(settings, vault, client)
    config = {
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_mode": "responses",
        "model": "synthetic-context-model",
        "encrypted_secret": b"not-a-real-ciphertext",
        "secret_context": "synthetic-context",
    }
    monkeypatch.setattr(service, "list", lambda: {"active_id": "synthetic-config"})
    monkeypatch.setattr(service, "_find", lambda _identity: dict(config))
    try:
        yield settings, service, client
    finally:
        assert folder.resolve().is_relative_to((ROOT / "runtime").resolve())
        if folder.exists():
            shutil.rmtree(folder)


def sent_context(body):
    return json.loads(next(item["content"] for item in body["input"] if item["role"] == "user"))


def test_parse_and_collaborate_receive_complete_read_only_catalog_overview(setup):
    settings, service, client = setup
    path = initialize_market(settings)
    original_bytes, original_mtime = path.read_bytes(), path.stat().st_mtime_ns
    categories, merchants = _read_store(path)
    merchant_counts = Counter(merchant["category"] for merchant in merchants)
    offering_counts = Counter(
        offer["category"] for merchant in merchants for offer in merchant["offerings"]
    )
    client.claimed_evidence = categories[0]["label"]
    original_context = {
        "confirmed_demand": {"desired_outcome": "Preserve the previously confirmed need"},
        "recent_messages": [],
    }
    frozen_context = copy.deepcopy(original_context)
    for collaborative in (False, True):
        result = service.parse_demand(
            "What can I discuss from the local catalog?",
            original_context,
            True,
            collaborative=collaborative,
        )
        body = client.requests[-1]
        overview = sent_context(body)["application_context"]["simulated_market"]
        assert overview["status"] == "available"
        assert overview["synthetic"] is True and overview["data_origin"] == "synthetic"
        assert overview["merchant_count"] == len(merchants) == 500
        assert overview["offering_count"] == sum(offering_counts.values()) == 1500
        assert overview["category_count"] == len(categories) == 50
        assert overview["categories"] == [
            {
                "id": category["id"],
                "label": category["label"],
                "label_en": category["label_en"],
                "merchant_count": merchant_counts[category["id"]],
                "offering_count": offering_counts[category["id"]],
            }
            for category in categories
        ]
        assert overview["catalog_overview_only"] is True
        assert overview["product_search_performed"] is False
        assert overview["real_supply_verified"] is False
        assert overview["offering_count_basis"] == (
            "merchant_offering_records_including_variants_and_services"
        )
        serialized = json.dumps(overview, ensure_ascii=False)
        assert len(serialized) <= 12000 and '"offerings"' not in serialized
        assert '"price"' not in serialized and '"capability"' not in serialized
        assert result["parsed"]["user_confirmed"] is False
        # Catalog labels never become user evidence even if a provider claims otherwise.
        assert result["parsed"]["required"][0]["source"] == "model_inferred"
        assert client.claimed_evidence not in client.evidence[-1]
        assert result["prompt_version"].endswith("+market-overview/1")
        instruction = body["input"][0]["content"]
        assert "NOT the number of distinct product types" in instruction
        assert "NOT a product search result" in instruction
        assert "never insert them as user requirements" in instruction
        assert body["store"] is False and "tools" not in body
    assert len(client.requests) == 2 and original_context == frozen_context
    assert path.read_bytes() == original_bytes and path.stat().st_mtime_ns == original_mtime
    assert not settings.database.exists()


def test_catalog_totals_and_bilingual_categories_are_derived_from_read_records(setup, monkeypatch):
    settings, _, _ = setup
    categories = [
        {
            "id": "alpha",
            "label": "合成甲类",
            "label_en": "Synthetic alpha",
            "merchant_count": 900,
            "offering_count": 900,
        },
        {
            "id": "beta",
            "label": "合成乙类",
            "label_en": "Synthetic beta",
            "merchant_count": 800,
            "offering_count": 800,
        },
    ]
    merchants = [
        {"category": "alpha", "offerings": [{"category": "alpha"}, {"category": "alpha"}]},
        {"category": "beta", "offerings": [{"category": "beta"}]},
    ]
    calls = []

    def controlled_read(path):
        calls.append(path)
        return categories, merchants

    monkeypatch.setattr(market_context, "_read_store", controlled_read)
    overview = market_context.build_market_context(settings)
    assert calls == [settings.data_dir / DATABASE_NAME]
    assert overview["merchant_count"] == 2 and overview["offering_count"] == 3
    assert overview["category_count"] == 2
    assert [category["merchant_count"] for category in overview["categories"]] == [1, 1]
    assert [category["offering_count"] for category in overview["categories"]] == [2, 1]
    assert [category["label"] for category in overview["categories"]] == ["合成甲类", "合成乙类"]
    assert [category["label_en"] for category in overview["categories"]] == [
        "Synthetic alpha",
        "Synthetic beta",
    ]
    assert not settings.data_dir.exists()


def test_missing_or_corrupt_market_degrades_without_inventing_counts_or_blocking_ai(setup):
    settings, service, client = setup
    path = settings.data_dir / DATABASE_NAME
    for corrupt in (False, True):
        if corrupt:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"SYNTHETIC_INVALID_DATABASE")
        result = service.parse_demand(
            "Can you explain the catalog coverage?",
            {"recent_messages": []},
            True,
            collaborative=corrupt,
        )
        overview = sent_context(client.requests[-1])["application_context"]["simulated_market"]
        assert overview["status"] == "unavailable"
        assert overview["reason"] == "market_catalog_unavailable"
        assert overview["merchant_count"] is None
        assert overview["offering_count"] is None
        assert overview["category_count"] is None
        assert overview["categories"] == []
        assert overview["product_search_performed"] is False
        assert overview["real_supply_verified"] is False
        assert result["parsed"]["user_confirmed"] is False
        assert (
            "do not infer zero or invent counts/categories"
            in client.requests[-1]["input"][0]["content"]
        )
        if corrupt:
            assert path.read_bytes() == b"SYNTHETIC_INVALID_DATABASE"
        else:
            assert not path.exists()
    assert len(client.requests) == 2 and not settings.database.exists()

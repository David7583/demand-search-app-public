"""Synthetic local snapshots only. No shopping APIs or production user data."""

import json
import shutil
from uuid import uuid4

import pytest
from demand_search.config import ROOT, Settings
from demand_search.errors import AppError
from demand_search.history_service import HistoryService
from demand_search.main import create_app
from demand_search.product_sources import ProductSearchPlanService, ProductSourceEntry
from demand_search.storage import connect, initialize
from fastapi.testclient import TestClient


def uid():
    return str(uuid4())


@pytest.fixture
def source_setup():
    folder = ROOT / "runtime" / ("test-sources-" + uuid4().hex)
    settings = Settings(data_dir=folder)
    initialize(settings)
    history = HistoryService(settings)
    conversation = history.create("Synthetic multi-item list")["id"]
    message = history.add_message(conversation, "Synthetic list only", uid())["message"]
    demand_id, version_id, other_version, item_a, item_b, removed = (uid() for _ in range(6))
    stamp = "2026-11-04T00:00:00.000000Z"
    snapshot = {
        "desired_outcome": "Synthetic home workspace",
        "items": [
            {
                "item_id": item_a,
                "name": "Synthetic chair",
                "status": "active",
                "source": "user_explicit",
                "confirmed": True,
            },
            {
                "item_id": item_b,
                "name": "Synthetic desk",
                "status": "active",
                "source": "user_explicit",
                "confirmed": True,
            },
            {"item_id": removed, "name": "Removed lamp", "status": "removed"},
        ],
    }
    with connect(settings) as db:
        db.execute(
            "INSERT INTO demands VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                demand_id,
                conversation,
                "local",
                uid(),
                uid(),
                "active",
                other_version,
                version_id,
                1,
                stamp,
                stamp,
            ),
        )
        for identity, number, status in [(version_id, 1, "confirmed"), (other_version, 2, "draft")]:
            db.execute(
                "INSERT INTO demand_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    demand_id,
                    number,
                    None,
                    message["id"],
                    message["content"],
                    json.dumps(snapshot),
                    status,
                    "synthetic",
                    "custom",
                    "synthetic/1",
                    stamp,
                ),
            )
    value = {
        "settings": settings,
        "service": ProductSearchPlanService(settings),
        "history": history,
        "conversation": conversation,
        "version": version_id,
        "draft": other_version,
        "item_a": item_a,
        "item_b": item_b,
        "removed": removed,
        "snapshot": snapshot,
    }
    try:
        yield value
    finally:
        assert folder.resolve().is_relative_to((ROOT / "runtime").resolve())
        shutil.rmtree(folder)


def mutate_snapshot(setup, value):
    with connect(setup["settings"]) as db:
        db.execute(
            "UPDATE demand_versions SET data_json=? WHERE id=?",
            (json.dumps(value), setup["version"]),
        )


def test_confirmed_snapshot_builds_only_plain_queries_and_fixed_platform_entries(
    source_setup, monkeypatch
):
    import socket
    import urllib.request

    def forbidden(*_args, **_kwargs):
        raise AssertionError("A local search plan must never make network requests")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    s = source_setup
    with connect(s["settings"]) as db:
        original = db.execute(
            "SELECT data_json FROM demand_versions WHERE id=?", (s["version"],)
        ).fetchone()[0]
    plan = s["service"].plan(s["conversation"], s["version"])
    assert plan["kind"] == "external_search_plan" and not plan["network_searched"]
    assert plan["offers"] == [] and plan["is_latest_confirmed"] and not plan["is_current_version"]
    assert [item["item_id"] for item in plan["items"]] == [s["item_a"], s["item_b"]]
    assert plan["items"][0]["query"] == "Synthetic chair"
    for item in plan["items"]:
        assert {v["id"] for v in item["sources"]} == {
            "jd",
            "taobao",
            "pinduoduo",
            "amazon_us",
            "ebay_us",
            "walmart_us",
            "etsy",
        }
        assert all(
            v["search_url"] is not None and v["status"] == "not_configured" for v in item["sources"]
        )
        assert all(v["link_kind"] == "keyword_search" for v in item["sources"])
    with connect(s["settings"]) as db:
        assert (
            db.execute(
                "SELECT data_json FROM demand_versions WHERE id=?", (s["version"],)
            ).fetchone()[0]
            == original
        )


def test_item_selection_is_bound_to_that_version(source_setup):
    s = source_setup
    result = s["service"].plan(s["conversation"], s["version"], [s["item_b"]])
    assert [i["item_id"] for i in result["items"]] == [s["item_b"]]
    for requested in [[s["removed"]], [uid()]]:
        with pytest.raises(AppError) as error:
            s["service"].plan(s["conversation"], s["version"], requested)
        assert error.value.code == "SEARCH_ITEM_NOT_FOUND"
    for requested in [[], [s["item_a"]] * 2, [uid() for _ in range(31)]]:
        with pytest.raises(AppError) as error:
            s["service"].plan(s["conversation"], s["version"], requested)
        assert error.value.code == "SEARCH_ITEMS_INVALID"


def test_draft_foreign_version_and_foreign_owner_fail_closed(source_setup):
    s = source_setup
    with pytest.raises(AppError) as error:
        s["service"].plan(s["conversation"], s["draft"])
    assert error.value.code == "DEMAND_CONFIRMATION_REQUIRED"
    b = s["history"].create()["id"]
    with pytest.raises(AppError) as error:
        s["service"].plan(b, s["version"])
    assert error.value.code == "DEMAND_VERSION_NOT_FOUND"
    with connect(s["settings"]) as db:
        db.execute(
            "UPDATE conversations SET owner_id='synthetic-other-owner' WHERE id=?",
            (s["conversation"],),
        )
    with pytest.raises(AppError) as error:
        s["service"].plan(s["conversation"], s["version"])
    assert error.value.code == "CONVERSATION_NOT_FOUND"


def test_withdrawn_or_all_removed_list_cannot_generate_new_plan(source_setup):
    s = source_setup
    snapshot = s["snapshot"]
    for item in snapshot["items"]:
        item["status"] = "removed"
    mutate_snapshot(s, snapshot)
    with pytest.raises(AppError) as error:
        s["service"].plan(s["conversation"], s["version"])
    assert error.value.code == "SEARCH_ITEMS_EMPTY"
    with connect(s["settings"]) as db:
        db.execute(
            "UPDATE demands SET status='withdrawn' WHERE conversation_id=?", (s["conversation"],)
        )
    with pytest.raises(AppError) as error:
        s["service"].plan(s["conversation"], s["version"])
    assert error.value.code == "DEMAND_WITHDRAWN"


def test_legacy_snapshot_without_items_is_not_rewritten(source_setup):
    s = source_setup
    mutate_snapshot(s, {"desired_outcome": "Legacy synthetic single requirement"})
    result = s["service"].plan(s["conversation"], s["version"])
    assert result["items"][0]["item_id"] is None
    assert result["items"][0]["query"] == "Legacy synthetic single requirement"
    with pytest.raises(AppError):
        s["service"].plan(s["conversation"], s["version"], [s["item_a"]])


def test_untrusted_name_cannot_change_external_destination(source_setup):
    s = source_setup
    injected = 'javascript:alert(1) https://evil.example/?next=%2F &keyword="test"'
    snapshot = s["snapshot"]
    snapshot["items"][0]["name"] = injected
    mutate_snapshot(s, snapshot)
    result = s["service"].plan(s["conversation"], s["version"], [s["item_a"]])
    assert result["items"][0]["query"] == injected
    assert {v["homepage_url"] for v in result["items"][0]["sources"]} == {
        "https://www.taobao.com/",
        "https://www.jd.com/",
        "https://mobile.yangkeduo.com/",
        "https://www.amazon.com/",
        "https://www.ebay.com/",
        "https://www.walmart.com/",
        "https://www.etsy.com/",
    }
    with pytest.raises(AppError) as error:
        ProductSourceEntry(
            "jd", "Synthetic invalid destination", "https://www.jd.com.evil.example/"
        ).plan_entry("Synthetic")
    assert error.value.code == "EXTERNAL_LINK_INVALID"


@pytest.mark.parametrize("name", ["", "x" * 201, "😀" * 101, "bad\x00query", "bad\x1bquery"])
def test_query_limits_fail_without_silent_truncation(source_setup, name):
    s = source_setup
    mutate_snapshot(s, {"desired_outcome": name})
    with pytest.raises(AppError):
        s["service"].plan(s["conversation"], s["version"])


def test_actual_root_middleware_and_request_validation(source_setup):
    s = source_setup
    app = create_app(s["settings"])
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 44000)) as client:
        url = f"/api/v1/conversations/{s['conversation']}/demand/search-plan"
        body = {"version_id": s["version"]}
        assert client.post(url, json=body).status_code == 401
        csrf = client.get("/api/v1/session").json()["csrf_token"]
        assert client.post(url, json=body).status_code == 403
        headers = {"X-DSA-CSRF": csrf}
        result = client.post(url, json=body, headers=headers)
        assert result.status_code == 200 and result.json()["offers"] == []
        assert (
            client.post(
                url, json=body, headers={**headers, "Origin": "https://untrusted.example"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                url, json={**body, "url": "https://untrusted.example"}, headers=headers
            ).status_code
            == 422
        )
        assert (
            client.post(
                url, json={**body, "item_ids": [uid() for _ in range(31)]}, headers=headers
            ).status_code
            == 422
        )
        assert (
            client.post(url, json={"version_id": "not-a-uuid"}, headers=headers).status_code == 422
        )
        assert (
            client.post(
                url.replace(s["conversation"], "not-a-uuid"), json=body, headers=headers
            ).status_code
            == 422
        )


def test_keyword_urls_encode_query_without_allowing_parameter_or_host_injection(source_setup):
    from urllib.parse import parse_qs, urlsplit

    s = source_setup
    name = "办公椅 &keyword=私人#片段 https://evil.example/"
    s["snapshot"]["items"][0]["name"] = name
    mutate_snapshot(s, s["snapshot"])
    item = s["service"].plan(s["conversation"], s["version"], [s["item_a"]])["items"][0]
    expected = {
        "taobao": ("s.taobao.com", "/search", "q"),
        "jd": ("search.jd.com", "/Search", "keyword"),
        "pinduoduo": ("mobile.yangkeduo.com", "/search_result.html", "search_key"),
        "amazon_us": ("www.amazon.com", "/s", "k"),
        "ebay_us": ("www.ebay.com", "/sch/i.html", "_nkw"),
        "walmart_us": ("www.walmart.com", "/search", "q"),
        "etsy": ("www.etsy.com", "/search", "q"),
    }
    for source in item["sources"]:
        link = urlsplit(source["search_url"])
        host, path, parameter = expected[source["id"]]
        assert link.scheme == "https" and link.netloc == host and link.path == path
        assert not link.fragment and parse_qs(link.query) == {parameter: [name]}
        assert source["sourceCoverageNote"]


def test_queries_use_only_confirmed_conditions_and_item_budget_not_total_or_original(source_setup):
    s = source_setup
    value = s["snapshot"]
    value["budget_ceiling"] = {
        "amount": 99000,
        "currency": "CNY",
        "source": "user_confirmed",
        "confirmed": True,
    }
    value["required"] = [{"text": "quiet", "source": "model_inferred", "confirmed": True}]
    item = value["items"][0]
    item["required"] = [
        {"text": "adjustable", "source": "user_explicit", "confirmed": True},
        {"text": "unreviewed inference", "source": "model_inferred", "confirmed": False},
        {"text": "unknown requirement", "source": "unknown", "confirmed": True},
    ]
    item["budget_ceiling"] = {
        "amount": 1200.50,
        "currency": "CNY",
        "source": "user_confirmed",
        "confirmed": True,
    }
    item["budget_basis"] = "unit"
    item["evidence"] = "PRIVATE RAW EVIDENCE"
    item["preferred"] = [
        {"text": "PRIVATE PREFERENCE", "source": "user_explicit", "confirmed": True}
    ]
    value["unknown"] = ["PRIVATE UNKNOWN"]
    mutate_snapshot(s, value)
    result = s["service"].plan(s["conversation"], s["version"])
    query = result["items"][0]["query"]
    assert query == "Synthetic chair quiet adjustable 单价上限1200.5 CNY"
    assert result["items"][1]["query"] == "Synthetic desk quiet"
    serialized = json.dumps(result)
    for excluded in [
        "99000",
        "unreviewed inference",
        "unknown requirement",
        "PRIVATE",
        "Synthetic list only",
    ]:
        assert excluded not in serialized
    assert result["items"][0]["query_notes"]


@pytest.mark.parametrize(
    "basis,confirmed,source",
    [
        ("unknown", True, "user_confirmed"),
        ("unit", False, "model_inferred"),
        ("unit", True, "unknown"),
    ],
)
def test_unknown_or_unconfirmed_budget_never_becomes_price_filter(
    source_setup, basis, confirmed, source
):
    s = source_setup
    item = s["snapshot"]["items"][0]
    item["budget_ceiling"] = {
        "amount": 3456,
        "currency": "CNY",
        "source": source,
        "confirmed": confirmed,
    }
    item["budget_basis"] = basis
    mutate_snapshot(s, s["snapshot"])
    result = s["service"].plan(s["conversation"], s["version"], [s["item_a"]])["items"][0]
    assert "3456" not in result["query"] and result["query_notes"]


def test_unconfirmed_name_and_long_combined_conditions_fail_without_truncation(source_setup):
    s = source_setup
    item = s["snapshot"]["items"][0]
    item["confirmed"] = False
    mutate_snapshot(s, s["snapshot"])
    with pytest.raises(AppError) as error:
        s["service"].plan(s["conversation"], s["version"], [s["item_a"]])
    assert error.value.code == "SEARCH_ITEM_UNCONFIRMED"
    item["confirmed"] = True
    item["required"] = [{"text": "r" * 200, "source": "user_confirmed", "confirmed": True}]
    mutate_snapshot(s, s["snapshot"])
    with pytest.raises(AppError) as error:
        s["service"].plan(s["conversation"], s["version"], [s["item_a"]])
    assert error.value.code == "SEARCH_QUERY_TOO_LONG"


@pytest.mark.parametrize(
    "provider,host,path,key,market",
    [
        ("amazon_us", "www.amazon.com", "/s", "k", "US"),
        ("ebay_us", "www.ebay.com", "/sch/i.html", "_nkw", "US"),
        ("walmart_us", "www.walmart.com", "/search", "q", "US"),
        ("etsy", "www.etsy.com", "/search", "q", "GLOBAL"),
    ],
)
def test_overseas_sources_preserve_exact_queries_and_never_claim_product_access(
    source_setup, provider, host, path, key, market
):
    from urllib.parse import parse_qs, urlsplit

    s = source_setup
    query = "Synthetic chair & budget=500 CNY ?# + 中文"
    snapshot = s["snapshot"]
    snapshot["items"][0]["name"] = query
    mutate_snapshot(s, snapshot)
    result = s["service"].plan(s["conversation"], s["version"], [s["item_a"]])
    item = result["items"][0]
    entry = next(source for source in item["sources"] if source["id"] == provider)
    url = urlsplit(entry["search_url"])
    assert url.scheme == "https" and url.netloc == host and url.path == path
    assert parse_qs(url.query) == {key: [query]} and not url.fragment
    assert entry["market"] == market and entry["label_en"]
    assert entry["status"] == "not_configured"
    assert result["network_searched"] is False and result["offers"] == []
    assert item["query"] == query
    assert result["sourceCoverageNote_en"] and entry["verification_note_en"]
    assert item["query_notes_en"] == []
    with connect(s["settings"]) as db:
        saved = json.loads(
            db.execute(
                "SELECT data_json FROM demand_versions WHERE id=?", (s["version"],)
            ).fetchone()[0]
        )
    assert saved == snapshot

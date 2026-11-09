"""S2.1 synthetic list regressions; no live data or provider calls."""

import copy
import json

import pytest
import test_demands
from demand_search.ai_demand import parse_demand
from demand_search.demand_service import DemandService
from demand_search.errors import AppError
from demand_search.storage import connect
from test_ai_demand import client_for, config
from test_ai_demand import data as ai_data
from test_demands import confirmation, parse, uid

setup = test_demands.setup


def item(name="chair", identity=None):
    return {
        "item_id": identity,
        "name": name,
        "quantity": 2,
        "unit": "pieces",
        "source": "user_explicit",
        "evidence": f"2 pieces {name}",
        "required": [],
        "preferred": [],
        "unknown": [],
        "budget_ceiling": None,
        "budget_basis": "unknown",
        "status": "active",
    }


def item_edits(value):
    result = {
        key: copy.deepcopy(value[key])
        for key in ("item_id", "name", "quantity", "unit", "unknown", "budget_basis", "status")
    }
    for key in ("required", "preferred"):
        result[key] = [fact["text"] for fact in value[key]]
    budget = value["budget_ceiling"]
    result["budget_ceiling"] = {k: budget[k] for k in ("amount", "currency")} if budget else None
    return result


def list_confirmation(version):
    request = confirmation(version)
    request["edits"]["items"] = [item_edits(value) for value in version["data"]["items"]]
    return request


@pytest.mark.parametrize("count", [20, 30])
def test_many_items_confirm_export_replay_and_reload(setup, count):
    service, history, models = setup
    conversation = history.create()["id"]
    models.output["items"] = [item(f"synthetic product {i}") for i in range(count)]
    original = "; ".join(value["evidence"] for value in models.output["items"])
    draft, body = parse(service, history, conversation, original)
    items = draft["current_version"]["data"]["items"]
    identities = {value["item_id"] for value in items}
    assert len(identities) == count and all(not value["confirmed"] for value in items)
    assert service.parse(conversation, body)["current_version"] == draft["current_version"]
    assert len(models.calls) == 1
    request = list_confirmation(draft["current_version"])
    approved = service.confirm(conversation, request)
    assert service.confirm(conversation, request)["duplicate"]
    assert all(value["confirmed"] for value in approved["current_version"]["data"]["items"])
    exported = service.export(conversation, True)
    packet = exported["packets"][0]
    assert packet["protocol"] == "ODIP/0.1.3-exp.1"
    assert packet["payload"]["original_text"] == original
    facts = packet["payload"]["constraints"]["specifications"]["demand_search_app_v1"]
    assert facts["shopping_list"]["budget_scope"] == "whole_list"
    assert {v["item_id"] for v in facts["shopping_list"]["items"]} == identities
    assert len(exported["packet_utf8"][0].encode()) < 65536
    assert DemandService(service.settings, models).export(conversation, True) == exported


def test_unconfirmed_followup_add_update_remove_and_total_budget(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    models.output["items"] = [item("chair"), item("desk")]
    first, _ = parse(service, history, conversation, "2 pieces chair and 2 pieces desk")
    first_items = first["current_version"]["data"]["items"]
    ids = [v["item_id"] for v in first_items]
    models.output["items"] = [
        {**item("chair", ids[0]), "quantity": 3, "evidence": "3 pieces chair"},
        item("lamp"),
    ]
    second, _ = parse(
        service,
        history,
        conversation,
        "add 2 pieces lamp; 3 pieces chair",
        first["current_version"]["id"],
    )
    assert models.calls[-1][1]["confirmed_demand"] is None
    assert models.calls[-1][1]["current_draft"]["items"] == first_items
    items = second["current_version"]["data"]["items"]
    names = {v["name"]: v for v in items}
    assert len(items) == 3 and names["desk"] == first_items[1]
    assert names["chair"]["item_id"] == ids[0] and names["chair"]["quantity"] == 3
    assert second["current_version"]["data"]["budget_ceiling"]["amount"] == 1500
    assert all(v["budget_ceiling"] is None for v in items)
    models.output["items"] = [{**item("desk", ids[1]), "status": "removed"}]
    third, _ = parse(service, history, conversation, "remove desk", second["current_version"]["id"])
    assert len(third["current_version"]["data"]["items"]) == 3
    assert third["confirmed_version"] is None
    assert not third["current_version"]["data"]["items"][0]["confirmed"]
    approved = service.confirm(conversation, list_confirmation(third["current_version"]))
    assert approved["current_version"]["data"]["items"][0]["status"] == "removed"
    assert approved["current_version"]["data"]["items"][0]["confirmed"]
    old = next(v for v in approved["versions"] if v["id"] == first["current_version"]["id"])
    assert old["data"]["items"] == first_items


@pytest.mark.parametrize("kind", ["foreign", "duplicate", "confirmed", "source", "limit"])
def test_invalid_items_preserve_old_version(setup, kind):
    service, history, models = setup
    conversation = history.create()["id"]
    models.output["items"] = [item()]
    old, _ = parse(service, history, conversation)
    identity = old["current_version"]["data"]["items"][0]["item_id"]
    models.output["items"] = [item(identity=identity)]
    if kind == "foreign":
        models.output["items"][0]["item_id"] = uid()
    elif kind == "duplicate":
        models.output["items"] *= 2
    elif kind == "confirmed":
        models.output["items"][0]["confirmed"] = True
    elif kind == "source":
        models.output["items"][0]["source"] = "user_confirmed"
    else:
        models.output["items"] = [item(str(i)) for i in range(31)]
    with pytest.raises(AppError):
        parse(service, history, conversation, "change", old["current_version"]["id"])
    assert service.get(conversation)["current_version"] == old["current_version"]


def test_one_item_edit_does_not_copy_total_budget_or_delete_omissions(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    models.output["items"] = [item("chair"), item("desk")]
    draft, _ = parse(service, history, conversation)
    request = list_confirmation(draft["current_version"])
    first = request["edits"]["items"][0]
    first.update(budget_ceiling={"amount": 300, "currency": "CNY"}, budget_basis="unit", quantity=4)
    request["edits"]["items"] = [first]
    approved = service.confirm(conversation, request)
    data = approved["current_version"]["data"]
    assert data["budget_ceiling"]["amount"] == 1500
    assert len(data["items"]) == 2 and data["items"][1]["budget_ceiling"] is None
    assert data["items"][0]["quantity"] == 4
    assert data["items"][0]["source"] == "user_confirmed"
    assert data["items"][0]["budget_ceiling"]["amount"] == 300
    assert data["items"][0]["budget_basis"] == "unit"
    assert not data["items"][1]["confirmed"]
    packet = service.export(conversation, True)["packets"][0]
    assert packet["payload"]["constraints"]["budget_ceiling"]["amount"] == 1500


def test_legacy_json_packet_bytes_unchanged_and_old_edits_keep_items(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    legacy, _ = parse(service, history, conversation)
    approved = service.confirm(conversation, confirmation(legacy["current_version"]))
    old_export = service.export(conversation, True)["packet_utf8"][0]
    with connect(service.settings) as db:
        rows = db.execute("SELECT id,data_json FROM demand_versions").fetchall()
        for row in rows:
            value = json.loads(row["data_json"])
            value.pop("items", None)
            db.execute(
                "UPDATE demand_versions SET data_json=? WHERE id=?", (json.dumps(value), row["id"])
            )
        before = dict(db.execute("SELECT id,data_json FROM demand_versions"))
    models.output["items"] = [item()]
    new, _ = parse(service, history, conversation, "add chair", approved["current_version"]["id"])
    newer = service.confirm(conversation, confirmation(new["current_version"]))
    assert newer["current_version"]["data"]["items"] == new["current_version"]["data"]["items"]
    assert not newer["current_version"]["data"]["items"][0]["confirmed"]
    assert service.export(conversation, True)["packet_utf8"][0] == old_export
    with connect(service.settings) as db:
        for identity, original in before.items():
            actual = db.execute(
                "SELECT data_json FROM demand_versions WHERE id=?", (identity,)
            ).fetchone()[0]
            assert actual == original


def test_item_evidence_and_bounded_output():
    value = ai_data()
    value["items"] = [item()]
    value["items"][0]["quantity"] = 500
    value["items"][0]["required"] = [
        {"text": "invented", "evidence": "invented", "source": "user_explicit"}
    ]
    value["items"][0]["budget_ceiling"] = {
        "amount": 900,
        "currency": "USD",
        "source": "user_explicit",
        "evidence": "900",
    }
    captured = []
    result = parse_demand(
        client_for(value, captured), config(), "synthetic-key", "2 pieces chair", {}
    )
    actual = result["parsed"]["items"][0]
    assert actual["source"] == actual["required"][0]["source"] == "model_inferred"
    assert actual["budget_ceiling"]["source"] == "model_inferred"
    assert captured[0]["max_output_tokens"] == 12288
    assert captured[0]["text"]["format"]["schema"]["properties"]["items"]["maxItems"] == 30


def test_large_packet_rejected_atomically_without_truncation(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    large = {
        **item(),
        "required": [{"text": "\u5bbd" * 500, "source": "model_inferred", "evidence": ""}] * 10,
    }
    models.output["items"] = [{**copy.deepcopy(large), "name": f"item{i}"} for i in range(30)]
    draft, _ = parse(service, history, conversation)
    with pytest.raises(AppError, match="NCP_MESSAGE_TOO_LARGE"):
        service.confirm(conversation, list_confirmation(draft["current_version"]))
    current = service.get(conversation)
    assert current["current_version"]["id"] == draft["current_version"]["id"]
    assert current["confirmed_version"] is None and len(current["versions"]) == 1


def test_assistant_reply_does_not_make_latest_user_stale(setup):
    service, history, models = setup
    conversation = history.create()["id"]
    models.output["items"] = [item()]
    draft, _ = parse(service, history, conversation)
    history.record_assistant(conversation, "synthetic local summary", {"source": "local-status"})
    result = service.confirm(conversation, list_confirmation(draft["current_version"]))
    assert result["current_version"]["user_confirmed"]

"""Synthetic history tests; never inspect the user's runtime database."""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from demand_search.config import ROOT, Settings
from demand_search.errors import AppError
from demand_search.history_routes import create_history_router
from demand_search.history_service import HistoryService
from demand_search.storage import connect, initialize
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


@pytest.fixture
def history():
    path = ROOT / "runtime" / ("test-history-" + uuid4().hex)
    settings = Settings(data_dir=path)
    initialize(settings)
    yield HistoryService(settings)
    assert path.resolve().is_relative_to((ROOT / "runtime").resolve())
    if path.exists():
        shutil.rmtree(path)


def test_new_a_b_restart_resume_keeps_original_and_context_isolated(history):
    a = history.create("synthetic A")
    original = "  Need a quiet computer under 1500.\nKeep this wording.  "
    first = history.add_message(a["id"], original, str(uuid4()))["message"]
    b = history.create("synthetic B")
    history.add_message(b["id"], "Need a chair, unrelated to A.", str(uuid4()))
    # New service/connection and idempotent migrations simulate application restart.
    initialize(history.settings)
    restarted = HistoryService(history.settings)
    assert restarted.get(a["id"])["messages"][0]["content"] == original
    second = restarted.add_message(a["id"], "Raise my budget to 3000.", str(uuid4()))["message"]
    assert second["sequence"] == 2 and first["sequence"] == 1
    assert len(restarted.get(b["id"])["messages"]) == 1
    context = restarted.get_context(a["id"])
    assert [item["content"] for item in context] == [original, "Raise my budget to 3000."]
    assert "chair" not in json.dumps(context)


def test_idempotency_conflicts_do_not_change_original(history):
    a, b = history.create(), history.create()
    identity = str(uuid4())
    one = history.add_message(a["id"], "synthetic unchanged text", identity)
    two = history.add_message(a["id"], "synthetic unchanged text", identity)
    assert one["duplicate"] is False and two["duplicate"] is True
    assert one["message"] == two["message"]
    for conversation_id, text in [(a["id"], "different"), (b["id"], "synthetic unchanged text")]:
        with pytest.raises(AppError) as caught:
            history.add_message(conversation_id, text, identity)
        assert caught.value.code == "MESSAGE_ID_CONFLICT"
    assert len(history.get(a["id"])["messages"]) == 1
    assert history.get(b["id"])["messages"] == []


def test_concurrent_sends_and_retries_have_unique_sequences(history):
    a = history.create()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda index: history.add_message(a["id"], "synthetic " + str(index), str(uuid4())),
                range(8),
            )
        )
    assert sorted(item["message"]["sequence"] for item in results) == list(range(1, 9))
    identity = str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as pool:
        retries = list(
            pool.map(
                lambda _: history.add_message(a["id"], "same synthetic retry", identity), range(4)
            )
        )
    assert sum(not item["duplicate"] for item in retries) == 1
    assert len(history.get(a["id"])["messages"]) == 9


def test_owned_queries_do_not_leak_other_owner(history):
    local = history.create("local visible")
    foreign = str(uuid4())
    with connect(history.settings) as db:
        db.execute(
            "INSERT INTO conversations(id,owner_id,title,created_at,updated_at) VALUES (?,?,?,?,?)",
            (foreign, "synthetic-other-owner", "private foreign title", "x", "x"),
        )
    for operation in (history.get, history.delete, history.export, history.get_context):
        with pytest.raises(AppError) as caught:
            operation(foreign)
        assert caught.value.code == "CONVERSATION_NOT_FOUND"
    assert [item["id"] for item in history.list()["conversations"]] == [local["id"]]
    history.delete_all()
    with connect(history.settings) as db:
        assert (
            db.execute("SELECT count(*) FROM conversations WHERE id=?", (foreign,)).fetchone()[0]
            == 1
        )


def test_export_delete_and_configuration_separation(history):
    a = history.create("synthetic export")
    history.add_message(a["id"], "synthetic private original", str(uuid4()))
    with connect(history.settings) as db:
        db.execute("CREATE TABLE synthetic_model_config(secret TEXT)")
        db.execute(
            "INSERT INTO synthetic_model_config VALUES (?)", ("SYNTHETIC-CONFIG-NOT-EXPORTED",)
        )
        assert db.execute("PRAGMA secure_delete").fetchone()[0] == 1
    data = history.export()
    assert data["includes_model_configuration"] is False
    assert "SYNTHETIC-CONFIG-NOT-EXPORTED" not in json.dumps(data)
    assert data["conversations"][0]["messages"][0]["content"] == "synthetic private original"
    history.delete(a["id"])
    assert history.list()["total"] == 0
    with connect(history.settings) as db:
        assert db.execute("SELECT count(*) FROM conversation_messages").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM synthetic_model_config").fetchone()[0] == 1
    history.create("to delete")
    result = history.delete_all()
    assert result["model_configurations_preserved"] is True
    with connect(history.settings) as db:
        assert db.execute("SELECT count(*) FROM synthetic_model_config").fetchone()[0] == 1


def test_search_literals_pagination_rename_and_context_limits(history):
    a = history.create("literal 100% _ token")
    b = history.create("another conversation")
    for text in ("first entry", "second entry", "third entry"):
        history.add_message(a["id"], text, str(uuid4()))
    history.add_message(b["id"], "unrelated", str(uuid4()))
    assert history.list("% _")["total"] == 1
    assert history.list("second")["conversations"][0]["id"] == a["id"]
    assert len(history.list(limit=1)["conversations"]) == 1
    assert history.rename(a["id"], "renamed")["title"] == "renamed"
    context = history.get_context(a["id"], max_messages=2, max_chars=15)
    assert len(context) == 2 and sum(len(item["content"]) for item in context) == 15
    assert context[-1]["content"] == "third entry"
    assert history.get(a["id"])["messages"][1]["content"] == "second entry"


def test_assistant_attribution_cannot_overwrite_or_cross_conversations(history):
    a, b = history.create(), history.create()
    parent = history.add_message(a["id"], "synthetic user text", str(uuid4()))["message"]
    answer = history.record_assistant(
        a["id"],
        "synthetic response",
        {"model": "test-model", "source": "ai"},
        parent_message_id=parent["id"],
    )
    assert answer["role"] == "assistant" and answer["parent_message_id"] == parent["id"]
    assert history.get(a["id"])["messages"][0]["content"] == "synthetic user text"
    with pytest.raises(AppError):
        history.record_assistant(b["id"], "bad association", parent_message_id=parent["id"])
    with pytest.raises(AppError):
        history.record_assistant(a["id"], "bad metadata", {"api_key": "synthetic"})


@pytest.mark.parametrize("value", ["", "   ", "x" * 8001, "bad\x00text", "\ud800"])
def test_invalid_content_rejected_without_partial_insert(history, value):
    a = history.create()
    with pytest.raises(AppError):
        history.add_message(a["id"], value, str(uuid4()))
    assert history.get(a["id"])["messages"] == []


def test_route_contract_and_owner_fields_rejected(history):
    # Isolated router contract test; root app separately verifies session/CSRF enforcement.
    app = FastAPI()
    app.include_router(create_history_router(history))

    @app.exception_handler(AppError)
    async def app_error(_request, exc):
        return JSONResponse({"error": {"code": exc.code}}, status_code=exc.status_code)

    with TestClient(app) as client:
        assert client.post("/api/v1/conversations", json={"owner_id": "other"}).status_code == 422
        response = client.post("/api/v1/conversations", json={"title": "contract"})
        assert response.status_code == 201
        identity = response.json()["id"]
        packet = {"content": "synthetic message", "client_message_id": str(uuid4())}
        assert (
            client.post(f"/api/v1/conversations/{identity}/messages", json=packet).status_code
            == 200
        )
        assert (
            client.get(f"/api/v1/conversations/{identity}/export").json()["scope"] == "conversation"
        )
        assert client.get("/api/v1/me/export").json()["scope"] == "all_conversations"
        assert client.delete("/api/v1/me/data").json()["model_configurations_preserved"] is True
        assert client.get("/api/v1/conversations").json()["total"] == 0
        assert client.get(f"/api/v1/conversations/{identity}").status_code == 404


def test_independent_process_restores_and_continues_history(history):
    import os
    import subprocess
    import sys

    conversation = history.create("synthetic process restart")
    history.add_message(conversation["id"], "original from first process", str(uuid4()))
    child_source = """
import json,sys
from pathlib import Path
from uuid import uuid4
from demand_search.config import Settings
from demand_search.storage import initialize
from demand_search.history_service import HistoryService
settings=Settings(data_dir=Path(sys.argv[1]))
initialize(settings)
service=HistoryService(settings)
original=service.get(sys.argv[2])
message=service.add_message(sys.argv[2],"continued in independent process",str(uuid4()))
print(json.dumps({"count_before":len(original["messages"]),"sequence":message["message"]["sequence"]}))
"""
    env = dict(os.environ, PYTHONPATH=str(ROOT / "apps/server/src"))
    result = subprocess.run(
        [sys.executable, "-c", child_source, str(history.settings.data_dir), conversation["id"]],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert json.loads(result.stdout) == {"count_before": 1, "sequence": 2}
    restored = history.get(conversation["id"])["messages"]
    assert [message["content"] for message in restored] == [
        "original from first process",
        "continued in independent process",
    ]

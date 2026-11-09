"""Independent security review regressions using synthetic data only."""

import asyncio
import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from uuid import uuid4

import pytest
from demand_search import storage
from demand_search.config import ROOT, Settings
from demand_search.errors import AppError
from demand_search.local_security import COOKIE_NAME, LocalSecurityMiddleware, LocalSessions
from demand_search.secret_vault import WindowsDPAPIVault
from starlette.responses import JSONResponse


def probe_middleware(headers, *, client="127.0.0.1", chunks=None, token_setup=False):
    sessions = LocalSessions()
    if token_setup:
        token, csrf = sessions.issue()
        headers = [
            (b"cookie", (COOKIE_NAME + "=" + token).encode()),
            (b"x-dsa-csrf", csrf.encode()),
            *headers,
        ]
    called, sent = [], []
    events = list(chunks or [{"type": "http.request", "body": b"{}", "more_body": False}])

    async def receive():
        return events.pop(0) if events else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    async def application(scope, receive, send):
        called.append(True)
        response = JSONResponse({"ok": True})
        await response(scope, receive, send)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/config/models/test",
        "query_string": b"",
        "root_path": "",
        "server": ("127.0.0.1", 8000),
        "client": (client, 12345),
        "headers": [(b"host", b"127.0.0.1:8000"), (b"content-type", b"application/json"), *headers],
    }
    asyncio.run(LocalSecurityMiddleware(application, sessions)(scope, receive, send))
    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    data = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return status, json.loads(data), called


@pytest.mark.parametrize(
    "origin", [b"null", b"https://untrusted.example", b"http://127.0.0.1:10086"]
)
def test_review_cross_origin_cannot_reach_provider_even_with_valid_tokens(origin):
    status, data, called = probe_middleware([(b"origin", origin)], token_setup=True)
    assert status == 403 and data["error"]["code"] == "ORIGIN_DENIED"
    assert called == []


def test_review_chunked_oversize_never_reaches_provider():
    chunks = [
        {"type": "http.request", "body": b"x" * 40000, "more_body": True},
        {"type": "http.request", "body": b"x" * 40000, "more_body": False},
    ]
    status, data, called = probe_middleware(
        [(b"origin", b"http://127.0.0.1:8000")], chunks=chunks, token_setup=True
    )
    assert status == 413 and data["error"]["code"] == "REQUEST_TOO_LARGE"
    assert called == []


def test_review_same_origin_valid_token_and_nonlocal_rejection():
    status, _, called = probe_middleware([(b"origin", b"http://127.0.0.1:8000")], token_setup=True)
    assert status == 200 and called == [True]
    status, data, called = probe_middleware([], client="192.0.2.1", token_setup=True)
    assert status == 403 and data["error"]["code"] == "LOCAL_ONLY" and called == []


@pytest.mark.skipif(not WindowsDPAPIVault.available, reason="Windows current-user DPAPI required")
def test_review_dpapi_context_and_integrity_are_not_portable_plaintext():
    vault = WindowsDPAPIVault()
    synthetic = "synthetic review credential " + str(uuid4())
    encrypted = vault.seal(synthetic, "synthetic-config-A")
    assert synthetic.encode() not in encrypted
    assert vault.unseal(encrypted, "synthetic-config-A") == synthetic
    with pytest.raises(AppError):
        vault.unseal(encrypted, "synthetic-config-B")
    damaged = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
    with pytest.raises(AppError):
        vault.unseal(damaged, "synthetic-config-A")


def test_review_concurrent_initializers_do_not_replay_migration(tmp_path, monkeypatch):
    # A private test migration directory; no production migration files are edited.
    migration_root = tmp_path / "synthetic-project"
    migrations = migration_root / "db/migrations"
    migrations.mkdir(parents=True)
    (migrations / "001_s0.sql").write_bytes((ROOT / "db/migrations/001_s0.sql").read_bytes())
    path = ROOT / "runtime" / ("test-review-migrations-" + uuid4().hex)
    settings = Settings(data_dir=path)
    monkeypatch.setattr(storage, "ROOT", migration_root)
    try:
        storage.initialize(settings)
        (migrations / "099_one_time.sql").write_text(
            "CREATE TABLE migration_once(value INTEGER);\nINSERT INTO migration_once VALUES (1);\n",
            encoding="utf-8",
        )
        original_connect = storage.connect
        barrier = threading.Barrier(2)

        class CursorValue:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

        class ConnectionProbe:
            def __init__(self, db):
                self.db = db

            def __getattr__(self, attr):
                return getattr(self.db, attr)

            def execute(self, sql, values=()):
                cursor = self.db.execute(sql, values)
                if sql.startswith("SELECT 1 FROM schema_migrations") and tuple(values) == (99,):
                    # Force the unsafe pre-lock check to race. A correct check under
                    # BEGIN IMMEDIATE already holds the lock and does not use the barrier.
                    if not self.db.in_transaction:
                        row = cursor.fetchone()
                        if row is None:
                            barrier.wait(timeout=5)
                        return CursorValue(row)
                return cursor

        @contextmanager
        def connected(value):
            with original_connect(value) as db:
                yield ConnectionProbe(db)

        monkeypatch.setattr(storage, "connect", connected)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(storage.initialize, settings) for _ in range(2)]
            errors = [result.exception() for result in futures]
        assert errors == [None, None], [type(error).__name__ if error else None for error in errors]
        with original_connect(settings) as db:
            assert db.execute("SELECT count(*) FROM migration_once").fetchone()[0] == 1
            assert (
                db.execute("SELECT count(*) FROM schema_migrations WHERE version=99").fetchone()[0]
                == 1
            )
    finally:
        assert path.resolve().is_relative_to((ROOT / "runtime").resolve())
        if path.exists():
            shutil.rmtree(path)

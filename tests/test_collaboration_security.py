"""The new streaming route must retain the existing model-call security gates."""

import shutil
from uuid import uuid4

from demand_search.config import ROOT, Settings
from demand_search.local_security import LocalSessions
from demand_search.main import create_app
from fastapi.testclient import TestClient


def test_collaboration_retains_session_csrf_origin_and_rate_limit(monkeypatch):
    folder = ROOT / "runtime" / ("test-stream-security-" + uuid4().hex)
    try:
        with TestClient(
            create_app(Settings(data_dir=folder)),
            base_url="http://127.0.0.1:18000",
            client=("127.0.0.1", 41000),
        ) as client:
            url = "/api/v1/conversations/" + str(uuid4()) + "/demand/collaborate"
            assert client.post(url, json={}).json()["error"]["code"] == "LOCAL_SESSION_REQUIRED"
            csrf = client.get("/api/v1/session").json()["csrf_token"]
            assert client.post(url, json={}).json()["error"]["code"] == "CSRF_REQUIRED"
            headers = {"X-DSA-CSRF": csrf, "Origin": "http://127.0.0.1:18000"}
            denied = client.post(
                url, json={}, headers={**headers, "Origin": "https://untrusted.invalid"}
            )
            assert denied.json()["error"]["code"] == "ORIGIN_DENIED"
            monkeypatch.setattr(LocalSessions, "allow_provider_call", lambda self: False)
            limited = client.post(url, json={}, headers=headers)
            assert limited.status_code == 429
            assert limited.json()["error"]["code"] == "REQUEST_RATE_LIMITED"
            assert limited.headers["cache-control"] == "no-store"
    finally:
        assert folder.resolve().is_relative_to((ROOT / "runtime").resolve())
        if folder.exists():
            shutil.rmtree(folder)

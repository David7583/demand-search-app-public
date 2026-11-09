"""Foundation regression checks using only synthetic data."""

import shutil
import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest
from demand_search.config import ROOT, Settings
from demand_search.main import create_app
from demand_search.storage import initialize
from fastapi.testclient import TestClient


@pytest.fixture
def settings():
    path = ROOT / "runtime" / ("test-" + uuid4().hex)
    value = Settings(data_dir=path)
    yield value
    # Only the exact synthetic test directory, checked below, is removed.
    assert path.resolve().is_relative_to((ROOT / "runtime").resolve())
    if path.exists():
        shutil.rmtree(path)


def test_bootstrap_persists_instance_across_restart(settings):
    initialize(settings)
    with closing(sqlite3.connect(settings.database)) as db:
        original = db.execute("SELECT value FROM app_metadata WHERE key='instance_id'").fetchone()
    initialize(settings)
    with closing(sqlite3.connect(settings.database)) as db:
        assert (
            db.execute("SELECT value FROM app_metadata WHERE key='instance_id'").fetchone()
            == original
        )
        assert db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 4


def test_local_status_does_not_claim_integrations(settings):
    with TestClient(
        create_app(settings), base_url="http://127.0.0.1", client=("127.0.0.1", 44000)
    ) as client:
        assert client.get("/healthz").json() == {"status": "ok", "stage": "S2"}
        result = client.get("/api/v1/status").json()
        assert result["ai_configured"] is False and result["search_enabled"] is False
        assert result["ncp"]["support"] == "local_intent_lifecycle_only"
        assert "runtime" not in str(result) and "secret" not in str(result)
        sources = client.get("/api/v1/providers/status").json()["providers"]
        assert {source["id"] for source in sources} == {
            "taobao",
            "jd",
            "pinduoduo",
            "amazon_us",
            "ebay_us",
            "walmart_us",
            "etsy",
        }
        assert all(source["status"] == "not_configured" for source in sources)
        csrf = client.get("/api/v1/session").json()["csrf_token"]
        assert client.post(
            "/api/v1/config/llm", json={"key": "synthetic-no-secret"}, headers={"X-DSA-CSRF": csrf}
        ).status_code in {404, 405}


def test_host_and_origin_boundaries(settings):
    with TestClient(
        create_app(settings), base_url="http://127.0.0.1", client=("127.0.0.1", 44000)
    ) as client:
        assert client.get("/healthz", headers={"host": "untrusted.example"}).status_code == 400
        response = client.get("/api/v1/status", headers={"origin": "https://untrusted.example"})
        assert "access-control-allow-origin" not in response.headers
        response = client.get("/api/v1/status", headers={"origin": "http://127.0.0.1:10086"})
        assert response.status_code == 403
        assert "access-control-allow-origin" not in response.headers


def test_hosted_and_external_data_directories_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="HOSTED_NOT_IMPLEMENTED"):
        Settings(mode="hosted")
    with pytest.raises(ValueError, match="DATA_DIRECTORY_OUTSIDE_PROJECT_RUNTIME"):
        Settings(data_dir=tmp_path)

"""Real DPAPI and local HTTP security boundaries using synthetic secrets only."""

import base64
import os
import shutil
import subprocess
import sys
from uuid import uuid4

import pytest
from demand_search.config import ROOT, Settings
from demand_search.errors import AppError
from demand_search.main import create_app
from demand_search.secret_vault import WindowsDPAPIVault
from fastapi.testclient import TestClient


@pytest.fixture
def settings():
    path = ROOT / "runtime" / ("test-security-" + uuid4().hex)
    yield Settings(data_dir=path)
    assert path.resolve().is_relative_to((ROOT / "runtime").resolve())
    if path.exists():
        shutil.rmtree(path)


def test_current_user_dpapi_roundtrip_tamper_and_cross_process(tmp_path):
    vault = WindowsDPAPIVault()
    secret = "synthetic-test-only-" + uuid4().hex
    protected = vault.seal(secret, "test-purpose")
    assert secret.encode() not in protected
    assert vault.unseal(protected, "test-purpose") == secret
    with pytest.raises(AppError):
        vault.unseal(protected, "other-purpose")
    with pytest.raises(AppError):
        vault.unseal(protected[:-1] + bytes([protected[-1] ^ 1]), "test-purpose")
    path = tmp_path / "ciphertext.bin"
    path.write_bytes(protected)
    env = dict(os.environ, PYTHONPATH=str(ROOT / "apps/server/src"))
    code = (
        "import sys; from pathlib import Path; "
        "from demand_search.secret_vault import WindowsDPAPIVault; "
        "import hashlib; "
        "value=WindowsDPAPIVault().unseal(Path(sys.argv[1]).read_bytes(),'test-purpose'); "
        "print(hashlib.sha256(value.encode()).hexdigest())"
    )
    import hashlib

    result = subprocess.check_output([sys.executable, "-c", code, str(path)], env=env, text=True)
    assert result.strip() == hashlib.sha256(secret.encode()).hexdigest()
    assert base64.b64encode(secret.encode()) not in protected


def test_session_csrf_origin_and_safe_validation(settings):
    with TestClient(
        create_app(settings), base_url="http://127.0.0.1:18000", client=("127.0.0.1", 41000)
    ) as client:
        assert client.get("/api/v1/config/models").status_code == 401
        assert (
            client.get(
                "/api/v1/session", headers={"origin": "https://attacker.example"}
            ).status_code
            == 403
        )
        boot = client.get("/api/v1/session")
        assert boot.status_code == 200
        assert "HttpOnly" in boot.headers["set-cookie"]
        assert "SameSite=strict" in boot.headers["set-cookie"]
        csrf = boot.json()["csrf_token"]
        assert client.get("/api/v1/config/models").json()["configs"] == []
        assert client.post("/api/v1/conversations", json={}).status_code == 403
        headers = {"X-DSA-CSRF": csrf, "Origin": "http://127.0.0.1:18000"}
        assert client.post("/api/v1/conversations", json={}, headers=headers).status_code == 201
        bad = client.post(
            "/api/v1/conversations", json={}, headers={**headers, "Origin": "https://evil.example"}
        )
        assert bad.status_code == 403
        invalid_secret = "synthetic-not-a-real-key"
        bad = client.post(
            "/api/v1/config/models/test", json={"api_key": invalid_secret}, headers=headers
        )
        assert bad.status_code == 422 and invalid_secret not in bad.text
        oversized = client.post(
            "/api/v1/conversations",
            content=b"x" * 65537,
            headers={**headers, "Content-Type": "application/json"},
        )
        assert oversized.status_code == 413
        result = client.get("/api/v1/status")
        assert result.headers["cache-control"] == "no-store"
        assert result.headers["x-frame-options"] == "DENY"


def test_non_loopback_denied_without_session(settings):
    with TestClient(
        create_app(settings), base_url="http://127.0.0.1", client=("192.168.1.12", 1234)
    ) as client:
        assert client.get("/api/v1/session").status_code == 403


def test_unexpected_errors_do_not_return_secret(settings):
    app = create_app(settings)

    @app.get("/api/v1/failing")
    async def broken():
        raise RuntimeError("synthetic-sensitive-value-must-not-leak")

    # The fixture route must precede the production static catch-all.
    app.router.routes.insert(0, app.router.routes.pop())
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 1234)) as client:
        client.get("/api/v1/session")
        result = client.get("/api/v1/failing")
        assert result.status_code == 500
        assert "synthetic-sensitive" not in result.text

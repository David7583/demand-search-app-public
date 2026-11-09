"""Synthetic provider and opaque test-vault tests; never real credentials."""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from demand_search.config import ROOT, Settings
from demand_search.errors import AppError
from demand_search.model_service import ModelService
from demand_search.providers import ProviderClient
from demand_search.storage import connect, initialize


class MemoryVault:
    """Test-only opaque vault. Production never selects this implementation."""

    def __init__(self):
        self.values = {}

    def seal(self, secret, context):
        token = uuid4().bytes
        self.values[(token, context)] = secret
        return token

    def unseal(self, value, context):
        return self.values[(value, context)]


class FakeClient:
    def __init__(self):
        self.fail = False
        self.calls = []

    def discover(self, config, key):
        self.calls.append(("discover", config["base_url"]))
        return {
            "models": [{"id": "synthetic-model"}],
            "discovery_supported": True,
            "note": "synthetic",
        }

    def parse(self, config, key, text):
        if self.fail:
            raise AppError("MODEL_KEY_INVALID", "Synthetic authentication failure.", 502)
        self.calls.append(("parse", text))
        return {
            "actual_model": "synthetic-model-snapshot",
            "parsed": {
                "original_text": text,
                "desired_outcome": "synthetic",
                "required": [],
                "preferred": [],
                "unknown": [],
                "user_confirmed": False,
            },
        }


@pytest.fixture
def setup():
    path = ROOT / "runtime" / ("test-models-" + uuid4().hex)
    settings = Settings(data_dir=path)
    initialize(settings)
    vault = MemoryVault()
    client = FakeClient()
    yield ModelService(settings, vault, client), settings, client, vault
    assert path.resolve().is_relative_to((ROOT / "runtime").resolve())
    shutil.rmtree(path)


def draft(**changes):
    data = {
        "name": "Synthetic profile",
        "provider": "custom",
        "base_url": "https://models.example.com/v1",
        "api_mode": "chat_completions",
        "model": "synthetic-model",
        "api_key": "synthetic-key-do-not-use",
        "existing_id": None,
        "consent": True,
        "test_text": "synthetic office chair",
    }
    data.update(changes)
    return data


def save_profile(service, **changes):
    ticket = service.test(draft(**changes))
    return service.save(ticket["validation_id"])


def test_test_does_not_save_and_single_use_ticket(setup):
    service, settings, _, _ = setup
    key = draft()["api_key"]
    ticket = service.test(draft())
    assert service.list() == {"configs": [], "active_id": None}
    assert key not in json.dumps(ticket)
    saved = service.save(ticket["validation_id"])
    assert saved["config"]["key_mask"] == "已安全保存"
    assert saved["active_id"] == saved["config"]["id"]
    assert key not in settings.database.read_bytes().decode("latin-1")
    assert key not in json.dumps(service.list())
    with pytest.raises(AppError, match="VALIDATION_EXPIRED"):
        service.save(ticket["validation_id"])


def test_failed_edit_preserves_previous_default_and_requires_new_key_for_new_host(setup):
    service, _, client, _ = setup
    original = save_profile(service)
    identifier = original["config"]["id"]
    client.fail = True
    with pytest.raises(AppError, match="MODEL_KEY_INVALID"):
        service.test(draft(existing_id=identifier, api_key=None, model="other"))
    assert service.list()["configs"][0]["model"] == "synthetic-model"
    assert service.list()["active_id"] == identifier
    with pytest.raises(AppError, match="NEW_KEY_REQUIRED"):
        service.test(
            draft(existing_id=identifier, api_key=None, base_url="https://other.example.com/v1")
        )


def test_saved_config_survives_service_restart_switch_and_delete(setup):
    service, settings, client, vault = setup
    first = save_profile(service)["config"]["id"]
    second = save_profile(service, name="second")["config"]["id"]
    again = ModelService(settings, vault, client)
    assert len(again.list()["configs"]) == 2
    assert again.activate(first) == {"active_id": first}
    assert again.parse("new synthetic text", True)["actual_model"] == "synthetic-model-snapshot"
    assert again.delete(first) == {"deleted": True, "active_id": None}
    assert again.list()["configs"][0]["id"] == second
    with pytest.raises(AppError, match="MODEL_NOT_CONFIGURED"):
        again.parse("hello", True)


def test_expired_and_stale_tickets_cannot_overwrite(setup):
    service, settings, _, _ = setup
    original = save_profile(service)["config"]["id"]
    first = service.test(draft(existing_id=original, api_key=None, model="first"))
    second = service.test(draft(existing_id=original, api_key=None, model="second"))
    service.save(second["validation_id"])
    with pytest.raises(AppError, match="CONFIG_CHANGED"):
        service.save(first["validation_id"])
    assert service.list()["configs"][0]["model"] == "second"
    ticket = service.test(draft())
    with connect(settings) as db:
        db.execute(
            "UPDATE model_validation_tickets SET expires_at='2000-01-01' WHERE id=?",
            (ticket["validation_id"],),
        )
    with pytest.raises(AppError, match="VALIDATION_EXPIRED"):
        service.save(ticket["validation_id"])


def test_consent_and_other_owner_access_rejected(setup):
    service, settings, client, _ = setup
    with pytest.raises(AppError, match="AI_CONSENT_REQUIRED"):
        service.discover(draft(consent=False))
    assert client.calls == []
    saved = save_profile(service)["config"]["id"]
    with connect(settings) as db:
        db.execute("UPDATE model_configs SET owner_id='other' WHERE id=?", (saved,))
    with pytest.raises(AppError, match="MODEL_CONFIG_NOT_FOUND"):
        service.activate(saved)
    assert service.list()["configs"] == []


def test_original_input_bound_and_inference_not_confirmation():
    client = ProviderClient()
    payload = {
        "desired_outcome": "safe chair",
        "required": [{"text": "ergonomic", "source": "user_explicit", "evidence": "fabricated"}],
        "preferred": [],
        "unknown": ["unknown material"],
    }
    key = 'synthetic-"quoted-key'
    payload["unknown"].append(key)
    client.request_json = lambda *args, **kw: {
        "model": "actual-snapshot",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}],
    }
    result = client.parse(draft(), key, "office chair")
    assert result["parsed"]["original_text"] == "office chair"
    assert result["parsed"]["user_confirmed"] is False
    assert result["parsed"]["required"][0]["source"] == "model_inferred"
    assert key not in str(result)


@pytest.mark.parametrize(
    "content", ['{"desired_outcome":"ok","unknown":[]}', "not-json", '{"a":1,"a":2}']
)
def test_invalid_model_content_is_not_verified(content):
    client = ProviderClient()
    client.request_json = lambda *args, **kw: {
        "model": "model",
        "choices": [{"message": {"content": content}}],
    }
    with pytest.raises(AppError, match="AI_SCHEMA_INVALID"):
        client.parse(draft(), "synthetic-key", "hello")


def test_concurrent_save_consumes_ticket_once(setup):
    service, _, _, _ = setup
    ticket = service.test(draft())["validation_id"]
    barrier = Barrier(2)

    def save():
        barrier.wait(timeout=3)
        try:
            service.save(ticket)
            return "saved"
        except AppError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(save), pool.submit(save)]
        outcomes = [item.result(timeout=10) for item in futures]
    assert sorted(outcomes) == ["VALIDATION_EXPIRED", "saved"]
    assert len(service.list()["configs"]) == 1


def test_delete_during_provider_call_does_not_resurrect_key(setup):
    service, settings, client, _ = setup
    identifier = save_profile(service)["config"]["id"]
    original_parse = client.parse

    def delete_and_parse(config, key, text):
        service.delete(identifier)
        return original_parse(config, key, text)

    client.parse = delete_and_parse
    with pytest.raises(AppError, match="CONFIG_CHANGED"):
        service.test(draft(existing_id=identifier, api_key=None))
    with connect(settings) as db:
        assert db.execute("SELECT COUNT(*) FROM model_validation_tickets").fetchone()[0] == 0
    assert service.list()["configs"] == []


def test_unavailable_secure_storage_does_not_spend_provider_call(setup):
    service, _, client, vault = setup

    def fail_to_seal(secret, context):
        raise AppError("SECRET_STORE_UNAVAILABLE", "Synthetic unavailable vault.", 503)

    vault.seal = fail_to_seal
    with pytest.raises(AppError, match="SECRET_STORE_UNAVAILABLE"):
        service.test(draft())
    assert client.calls == []

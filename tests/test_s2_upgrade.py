"""Upgrade a synthetic S1 database without losing DPAPI configurations or conversations."""

import shutil
from uuid import uuid4

from demand_search import storage
from demand_search.config import ROOT, Settings
from demand_search.history_service import HistoryService
from demand_search.model_service import ModelService
from demand_search.secret_vault import WindowsDPAPIVault


class ModelFixture:
    def parse(self, config, key, text):
        assert key == "synthetic-upgrade-only-key"
        return {
            "actual_model": "synthetic-model",
            "parsed": {
                "original_text": text,
                "desired_outcome": "synthetic",
                "required": [],
                "preferred": [],
                "unknown": [],
                "user_confirmed": False,
            },
        }


def test_s1_to_s2_migration_preserves_private_history_and_encrypted_config(tmp_path, monkeypatch):
    old_root = tmp_path / "s1-fixture"
    migration_dir = old_root / "db/migrations"
    migration_dir.mkdir(parents=True)
    for name in ("001_s0.sql", "002_model_configs.sql", "003_conversations.sql"):
        shutil.copyfile(ROOT / "db/migrations" / name, migration_dir / name)
    path = ROOT / "runtime" / ("test-s2-upgrade-" + uuid4().hex)
    settings = Settings(data_dir=path)
    try:
        monkeypatch.setattr(storage, "ROOT", old_root)
        storage.initialize(settings)
        history = HistoryService(settings)
        conversation = history.create("synthetic existing S1")["id"]
        message = history.add_message(conversation, "original S1 message", str(uuid4()))
        models = ModelService(settings, WindowsDPAPIVault(), ModelFixture())
        ticket = models.test(
            {
                "name": "synthetic old profile",
                "provider": "custom",
                "base_url": "https://models.example.com/v1",
                "api_mode": "chat_completions",
                "model": "synthetic-model",
                "api_key": "synthetic-upgrade-only-key",
                "consent": True,
                "test_text": "synthetic setup",
            }
        )
        saved = models.save(ticket["validation_id"])["active_id"]
        before = history.get(conversation)
        monkeypatch.setattr(storage, "ROOT", ROOT)
        storage.initialize(settings)
        storage.initialize(settings)
        assert history.get(conversation) == before
        assert before["messages"][0]["id"] == message["message"]["id"]
        assert models.list()["active_id"] == saved
        assert models.parse("synthetic after upgrade", True)["actual_model"] == "synthetic-model"
        with storage.connect(settings) as db:
            assert db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 4
            assert db.execute("SELECT count(*) FROM demand_versions").fetchone()[0] == 0
        assert b"synthetic-upgrade-only-key" not in settings.database.read_bytes()
    finally:
        assert path.resolve().is_relative_to((ROOT / "runtime").resolve())
        if path.exists():
            shutil.rmtree(path)

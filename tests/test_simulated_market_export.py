"""Two targeted checks for the exact synthetic SQLite publication exception."""

import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_simulated_market  # noqa: E402
from export_simulated_market import EXPORT_RELATIVE_PATH, export_seed  # noqa: E402
from scan_secrets import MANIFEST_NAME, _inspect, _scan_archive  # noqa: E402


def test_exact_seed_passes_index_and_manifest_and_reexport_reuses_it(tmp_path, monkeypatch):
    def serializer_must_not_run():
        raise AssertionError("Validating an approved snapshot must not depend on its serializer")

    monkeypatch.setattr(export_simulated_market, "_new_seed_bytes", serializer_must_not_run)
    artifact = ROOT / EXPORT_RELATIVE_PATH
    data, modified = artifact.read_bytes(), artifact.stat().st_mtime_ns
    digest = hashlib.sha256(data).hexdigest()
    assert export_seed() == {"path": EXPORT_RELATIVE_PATH, "sha256": digest, "reused": True}
    assert artifact.stat().st_mtime_ns == modified and artifact.read_bytes() == data
    findings, counts = [], {"index": 0}
    _inspect(EXPORT_RELATIVE_PATH, data, "index", findings, counts)
    assert findings == [] and counts == {"index": 1}
    target = tmp_path / EXPORT_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(data)
    (tmp_path / MANIFEST_NAME).write_text(
        json.dumps({"files": [{"path": EXPORT_RELATIVE_PATH, "sha256": digest}]}),
        encoding="utf-8",
    )
    assert _scan_archive(tmp_path, MANIFEST_NAME)["passed"] is True


def test_malicious_index_bytes_and_other_sqlite_paths_are_rejected():
    # The valid working-tree file remains unchanged while staged bytes differ.
    artifact = ROOT / EXPORT_RELATIVE_PATH
    original = artifact.read_bytes()
    with closing(sqlite3.connect(":memory:")) as db:
        db.deserialize(original)
        db.execute("CREATE TABLE private_queries(content TEXT)")
        db.execute("INSERT INTO private_queries VALUES ('SYNTHETIC_NEGATIVE_CANARY')")
        db.commit()
        corrupted = db.serialize()
    for name, data, reason in [
        (EXPORT_RELATIVE_PATH, corrupted, "invalid synthetic seed database"),
        (EXPORT_RELATIVE_PATH, original + b"SYNTHETIC_TRAILER", "invalid synthetic seed database"),
        ("data/simulated-market/other.sqlite3", original, "sensitive file type"),
        ("runtime/demand-search.sqlite3", original, "sensitive file type"),
    ]:
        findings, counts = [], {"index": 0}
        _inspect(name, data, "index", findings, counts)
        assert any(row["reason"] == reason for row in findings)
    assert artifact.read_bytes() == original

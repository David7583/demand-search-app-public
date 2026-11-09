"""Source archives verify only their explicit reviewed bytes, without Git state."""

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("archive_gate", ROOT / "scripts/scan_secrets.py")
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


def write_manifest(root, files=None):
    files = files or {"README.md": b"Synthetic archive\n", "src/example.py": b"pass\n"}
    entries = []
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        entries.append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
    (root / scanner.MANIFEST_NAME).write_text(
        json.dumps({"format": "review-manifest/1", "files": entries}), encoding="utf-8"
    )
    return entries


def codes(result):
    return {entry.get("code") for entry in result["findings"]}


def test_archive_passes_without_git_and_does_not_grant_release(tmp_path, monkeypatch):
    write_manifest(tmp_path)
    monkeypatch.setattr(
        scanner.subprocess, "run", lambda *args, **kwargs: pytest.fail("Archive consulted Git")
    )
    result = scanner.scan(tmp_path, scanner.MANIFEST_NAME)
    assert result["passed"] and result["files_scanned_by_scope"] == {"manifest": 2}
    assert result["mode"] == "source-manifest"
    assert result["history_scanned"] is False and result["release_authorized"] is False


def test_default_mode_rejects_parent_git_but_explicit_archive_is_independent(tmp_path):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    archive = tmp_path / "unpacked"
    archive.mkdir()
    write_manifest(archive)
    assert codes(scanner.scan(archive)) == {"GIT_ROOT_MISMATCH"}
    assert scanner.scan(archive, scanner.MANIFEST_NAME)["passed"]


def test_hash_missing_extra_and_ignored_source_cannot_bypass_review(tmp_path):
    write_manifest(tmp_path)
    (tmp_path / "README.md").write_text("Changed\n")
    (tmp_path / "src/example.py").unlink()
    (tmp_path / ".gitignore").write_text("extra.py\n")
    (tmp_path / "extra.py").write_text("pass\n")
    result = scanner.scan(tmp_path, scanner.MANIFEST_NAME)
    assert {
        "SOURCE_FILE_HASH_MISMATCH",
        "SOURCE_MISSING_FILE",
        "SOURCE_EXTRA_FILE",
    } <= codes(result)
    assert any(row.get("path") == "extra.py" for row in result["findings"])


def test_same_secret_rules_apply_to_archive_without_disclosing_material(tmp_path):
    synthetic = "sk-" + "X" * 40
    write_manifest(tmp_path, {"sample.txt": synthetic.encode()})
    result = scanner.scan(tmp_path, scanner.MANIFEST_NAME)
    assert not result["passed"]
    assert any(row["reason"] == "secret-like material" for row in result["findings"])
    assert synthetic not in str(result)


@pytest.mark.parametrize(
    "unsafe",
    [
        "../escape.py",
        "/absolute.py",
        "C:/escape.py",
        "src/unsafe?.py",
        "src/\ud800.py",
        "src\\escape.py",
        "src//escape.py",
        "src/../escape.py",
        "src/CON.txt",
        "trailing./example.py",
        ".local/secrets.json",
        ".git/config",
        "runtime/private.sqlite",
        ".env",
        "REVIEW-MANIFEST.json",
    ],
)
def test_unsafe_manifest_is_rejected_before_reading_any_source(tmp_path, monkeypatch, unsafe):
    write_manifest(tmp_path)
    (tmp_path / scanner.MANIFEST_NAME).write_text(
        json.dumps({"files": [{"path": unsafe, "sha256": "0" * 64}]}), encoding="utf-8"
    )
    monkeypatch.setattr(
        Path, "read_bytes", lambda *args, **kwargs: pytest.fail("Unsafe manifest opened source")
    )
    result = scanner.scan(tmp_path, scanner.MANIFEST_NAME)
    assert not result["passed"] and result["files_scanned_by_scope"]["manifest"] == 0


def test_duplicates_case_collisions_invalid_hash_and_external_manifest_fail(tmp_path):
    entries = write_manifest(tmp_path)
    entries.append({"path": "readme.md", "sha256": "0" * 64})
    entries.append({"path": "other.py", "sha256": "not-a-digest"})
    (tmp_path / scanner.MANIFEST_NAME).write_text(json.dumps({"files": entries}), encoding="utf-8")
    result = scanner.scan(tmp_path, scanner.MANIFEST_NAME)
    assert {"SOURCE_PATH_UNSAFE", "SOURCE_MANIFEST_INVALID"} <= codes(result)
    assert codes(scanner.scan(tmp_path, "../REVIEW-MANIFEST.json")) == {"SOURCE_MANIFEST_INVALID"}


def test_private_generated_directories_are_not_entered_and_extra_env_is_not_read(
    tmp_path, monkeypatch
):
    write_manifest(tmp_path)
    for folder in (".local", ".venv", "runtime", "node_modules", "dist", ".git"):
        path = tmp_path / folder
        path.mkdir()
        (path / "private.txt").write_text("do not inspect")
    (tmp_path / ".env").write_text("do not inspect")
    original = Path.read_bytes

    def guarded(path):
        if path.name == ".env" or path.name == "private.txt":
            pytest.fail("Private material was read")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    result = scanner.scan(tmp_path, scanner.MANIFEST_NAME)
    assert codes(result) == {"SOURCE_PRIVATE_PATH"}
    assert len(result["findings"]) == 1 and result["findings"][0]["path"] == ".env"


def test_linked_manifest_and_linked_sources_are_rejected_without_following(tmp_path, monkeypatch):
    write_manifest(tmp_path)
    monkeypatch.setattr(scanner, "_linked", lambda path: path.name == scanner.MANIFEST_NAME)
    assert codes(scanner.scan(tmp_path, scanner.MANIFEST_NAME)) == {"SOURCE_MANIFEST_INVALID"}
    monkeypatch.setattr(scanner, "_linked", lambda path: path.name == "src")
    result = scanner.scan(tmp_path, scanner.MANIFEST_NAME)
    assert "SOURCE_SYMLINK" in codes(result)
    assert result["files_scanned_by_scope"]["manifest"] == 1


@pytest.mark.parametrize("contents", ["{}", "[]", '{"files":[]}', "not json"])
def test_malformed_manifest_fails_closed(tmp_path, contents):
    (tmp_path / scanner.MANIFEST_NAME).write_text(contents, encoding="utf-8")
    assert codes(scanner.scan(tmp_path, scanner.MANIFEST_NAME)) == {"SOURCE_MANIFEST_INVALID"}


def load_verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("archive_verifier", ROOT / "scripts/verify.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    return verifier


def test_verifier_records_manifest_and_git_dirty_state_without_listing_private_names(
    tmp_path, monkeypatch
):
    verifier = load_verifier(monkeypatch)
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    write_manifest(tmp_path)
    manifest = tmp_path / scanner.MANIFEST_NAME
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    metadata["source_commit"] = "a" * 40
    manifest.write_text(json.dumps(metadata), encoding="utf-8")
    snapshot = verifier.source_snapshot(scanner.MANIFEST_NAME)
    assert snapshot["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert snapshot["source_commit"] == "a" * 40
    assert snapshot["publication_authorized"] is False
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / "synthetic-private-filename").write_text("synthetic only")
    snapshot = verifier.source_snapshot()
    assert snapshot["kind"] == "git" and snapshot["worktree_dirty"] is True
    assert "synthetic-private-filename" not in str(snapshot)


def test_verifier_passes_archive_parameter_and_keeps_full_checks(tmp_path, monkeypatch):
    verifier = load_verifier(monkeypatch)
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    monkeypatch.setattr(verifier, "require_project_environment", lambda: None)
    monkeypatch.setattr(
        verifier.sys,
        "argv",
        ["verify.py", "--stage", "S5", "--browser", "--source-manifest", scanner.MANIFEST_NAME],
    )
    write_manifest(tmp_path)
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as result:
        verifier.main()
    assert result.value.code is False
    assert commands[-1][-2:] == ["--source-manifest", scanner.MANIFEST_NAME]
    assert len(commands) == 14
    assert any("pytest" in command for command in commands)
    assert any("build:h5" in command for command in commands)
    assert any("build:weapp" in command for command in commands)
    assert any("test:browser" in command for command in commands)
    report = json.loads(
        (tmp_path / ".local/logs/s5-validation/s5-verification.json").read_text(encoding="utf-8")
    )
    assert (
        report["source_snapshot"]["manifest_sha256"]
        == report["source_snapshot_after"]["manifest_sha256"]
    )
    assert report["public_deployment_blocked"] is True


def test_desktop_verifier_excludes_paused_targets(tmp_path, monkeypatch):
    verifier = load_verifier(monkeypatch)
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    monkeypatch.setattr(verifier, "require_project_environment", lambda: None)
    monkeypatch.setattr(verifier, "source_snapshot", lambda *args: {"kind": "synthetic"})
    monkeypatch.setattr(
        verifier.sys, "argv", ["verify.py", "--stage", "S5", "--browser", "--target", "desktop"]
    )
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        assert kwargs["env"]["DSA_VERIFY_DESKTOP"] == "1"
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as result:
        verifier.main()
    assert result.value.code is False
    assert len(commands) == 13
    assert not any("build:weapp" in command for command in commands)
    browser = next(command for command in commands if "test:browser" in command)
    assert browser[-2:] == ["--", "--project=desktop-edge"]
    assert any("pytest" in command for command in commands)
    assert any("build:h5" in command for command in commands)
    report = json.loads(
        (tmp_path / ".local/logs/s5-desktop-validation/s5-verification.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["target"] == "desktop" and report["other_platform_work_paused"] is True

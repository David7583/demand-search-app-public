"""Reviewed maintenance distributions remain visible and receive full secret scanning."""

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "maintained_source_gate", ROOT / "scripts/scan_secrets.py"
)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)
MAINTAINED = (
    "apps/client/tooling/taro-vite-runner/dist",
    "apps/client/tooling/taro-plugin-framework-react/dist",
)


def write_file(root, name, contents=b"/* synthetic source */\n"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    return path


def write_manifest(root, files):
    entries = []
    for name, contents in files.items():
        write_file(root, name, contents)
        entries.append({"path": name, "sha256": hashlib.sha256(contents).hexdigest()})
    (root / scanner.MANIFEST_NAME).write_text(json.dumps({"files": entries}), encoding="utf-8")


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)


def prepare_git(root):
    assert git(root, "init", "--quiet").returncode == 0
    (root / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())


def codes(result):
    return {row.get("code") for row in result["findings"]}


@pytest.mark.parametrize("prefix", MAINTAINED)
def test_only_reviewed_dist_is_visible_to_normal_git_add(tmp_path, prefix):
    prepare_git(tmp_path)
    source = prefix + "/h5/example.js"
    write_file(tmp_path, source)
    assert git(tmp_path, "check-ignore", "--quiet", "--no-index", source).returncode == 1
    assert git(tmp_path, "add", source).returncode == 0
    assert source.encode() in git(tmp_path, "ls-files", "-z").stdout


@pytest.mark.parametrize(
    "name",
    [
        "dist/example.js",
        "apps/client/dist/example.js",
        "apps/client/tooling/unreviewed/dist/example.js",
        "apps/client/tooling/taro-vite-runner-extra/dist/example.js",
        MAINTAINED[0] + "/nested/dist/example.js",
        MAINTAINED[0] + "/runtime/example.js",
        MAINTAINED[1] + "/node_modules/example.js",
        MAINTAINED[1] + "/.env",
    ],
)
def test_other_dist_and_private_children_stay_ignored_and_unpublishable(tmp_path, name):
    prepare_git(tmp_path)
    write_file(tmp_path, name)
    assert git(tmp_path, "check-ignore", "--quiet", "--no-index", name).returncode == 0
    assert scanner._private_path(name) or scanner._sensitive_file(Path(name).name)


@pytest.mark.parametrize("prefix", MAINTAINED)
def test_reviewed_dist_is_content_scanned_in_git_index_and_worktree(tmp_path, prefix):
    prepare_git(tmp_path)
    name = prefix + "/example.js"
    synthetic_secret = ("sk-" + "X" * 40).encode()
    write_file(tmp_path, name, synthetic_secret)
    assert git(tmp_path, "add", name).returncode == 0
    result = scanner.scan(tmp_path)
    assert not result["passed"]
    matches = [
        row
        for row in result["findings"]
        if row.get("path") == name and row["reason"] == "secret-like material"
    ]
    assert {row["scope"] for row in matches} == {"index", "worktree"}
    assert not any(row["reason"] == "private directory tracked" for row in matches)
    assert synthetic_secret.decode() not in str(result)


@pytest.mark.parametrize("prefix", MAINTAINED)
def test_reviewed_archive_source_passes_then_secret_is_still_detected(tmp_path, prefix):
    name = prefix + "/nested/source.js"
    write_manifest(tmp_path, {name: b"/* synthetic */\n"})
    result = scanner.scan(tmp_path, scanner.MANIFEST_NAME)
    assert result["passed"] and result["files_scanned_by_scope"] == {"manifest": 1}
    synthetic_secret = ("github_pat_" + "Y" * 40).encode()
    write_manifest(tmp_path, {name: synthetic_secret})
    result = scanner.scan(tmp_path, scanner.MANIFEST_NAME)
    assert not result["passed"]
    assert any(row["reason"] == "secret-like material" for row in result["findings"])
    assert synthetic_secret.decode() not in str(result)


@pytest.mark.parametrize(
    "suffix",
    [
        "runtime/private.json",
        "nested/dist/private.js",
        "node_modules/private.js",
        ".git/config",
        ".env",
        "nested/.env",
        "nested/.env.secret/private.json",
        "key.pem",
    ],
)
def test_listed_private_material_under_maintained_dist_is_rejected_before_read(
    tmp_path, monkeypatch, suffix
):
    name = MAINTAINED[0] + "/" + suffix
    write_manifest(tmp_path, {name: b"private fixture must not be read"})
    monkeypatch.setattr(
        Path, "read_bytes", lambda *args, **kwargs: pytest.fail("Private source was read")
    )
    result = scanner.scan(tmp_path, scanner.MANIFEST_NAME)
    assert codes(result) == {"SOURCE_PRIVATE_PATH"}
    assert result["files_scanned_by_scope"] == {"manifest": 0}


@pytest.mark.parametrize(
    "name",
    [
        "dist/example.js",
        "apps/client/dist/example.js",
        "apps/client/tooling/other/dist/example.js",
        ".local/" + MAINTAINED[0] + "/example.js",
    ],
)
def test_archive_does_not_extend_the_exception_to_other_distribution_paths(tmp_path, name):
    write_manifest(tmp_path, {name: b"/* synthetic */"})
    result = scanner.scan(tmp_path, scanner.MANIFEST_NAME)
    assert codes(result) == {"SOURCE_PRIVATE_PATH"}
    assert result["files_scanned_by_scope"] == {"manifest": 0}


@pytest.mark.parametrize("prefix", MAINTAINED)
def test_extra_source_inside_reviewed_dist_cannot_hide_from_archive_manifest(tmp_path, prefix):
    known = prefix + "/known.js"
    extra = prefix + "/nested/extra.js"
    write_manifest(tmp_path, {known: b"/* reviewed synthetic */"})
    write_file(tmp_path, extra)
    result = scanner.scan(tmp_path, scanner.MANIFEST_NAME)
    assert codes(result) == {"SOURCE_EXTRA_FILE"}
    assert result["findings"][0]["path"] == extra


@pytest.mark.parametrize("private_dir", ["runtime", ".git", ".env.hidden", "nested/dist"])
def test_unlisted_private_directory_inside_reviewed_dist_fails_without_entering(
    tmp_path, monkeypatch, private_dir
):
    prefix = MAINTAINED[1]
    write_manifest(tmp_path, {prefix + "/known.js": b"/* reviewed synthetic */"})
    directory = tmp_path / prefix / private_dir
    write_file(tmp_path, prefix + "/" + private_dir + "/private.json")
    original = scanner.os.scandir

    def guarded(path):
        if Path(path) == directory:
            pytest.fail("Entered private directory")
        return original(path)

    monkeypatch.setattr(scanner.os, "scandir", guarded)
    result = scanner.scan(tmp_path, scanner.MANIFEST_NAME)
    assert codes(result) == {"SOURCE_PRIVATE_PATH"}
    assert result["findings"][0]["path"] == prefix + "/" + private_dir

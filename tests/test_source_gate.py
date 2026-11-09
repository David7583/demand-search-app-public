"""A clean worktree must never hide a staged synthetic credential."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("source_gate", ROOT / "scripts/scan_secrets.py")
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


@pytest.mark.parametrize("worktree_action", ["replace", "delete"])
def test_staged_secret_detected_after_worktree_cleanup(tmp_path, worktree_action):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    source = tmp_path / "sample.txt"
    synthetic = "sk-" + "A" * 40
    source.write_text(synthetic, encoding="utf-8")
    subprocess.run(["git", "add", "--", "sample.txt"], cwd=tmp_path, check=True)
    if worktree_action == "replace":
        source.write_text("clean", encoding="utf-8")
    else:
        source.unlink()
    result = scanner.scan(tmp_path)
    assert result["passed"] is False
    assert any(item["scope"] == "index" for item in result["findings"])
    assert synthetic not in str(result)


def test_untracked_secret_detected(tmp_path):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / "sample.txt").write_text("sk-" + "B" * 40, encoding="utf-8")
    result = scanner.scan(tmp_path)
    assert result["passed"] is False
    assert result["findings"][0]["scope"] == "worktree"

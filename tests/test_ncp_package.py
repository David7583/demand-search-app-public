"""Ensure a clean checkout keeps the exact upstream bytes, not only this worktree."""

import hashlib
import json
import subprocess

import pytest
from demand_search.config import ROOT


def test_git_index_preserves_pinned_ncp_asset_bytes():
    check = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=ROOT, capture_output=True, text=True
    )
    if check.returncode != 0:
        pytest.skip("Source archive has no Git index; working asset integrity is tested separately")
    from pathlib import Path

    if Path(check.stdout.strip()).resolve() != ROOT.resolve():
        pytest.skip("No independent application Git index in this source archive")
    locked = json.loads((ROOT / "config/ncp-import-lock.json").read_text(encoding="utf-8"))
    for entry in locked["files"]:
        raw = subprocess.check_output(["git", "show", ":" + entry["path"]], cwd=ROOT)
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], entry["path"]

"""Repeat the S2 checks; store real exit codes and local logs."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from check_environment import require_project_environment

ROOT = Path(__file__).resolve().parents[1]


def source_snapshot(manifest_name=None):
    if manifest_name is not None:
        manifest = ROOT / manifest_name
        try:
            if (
                manifest.is_symlink()
                or manifest.is_junction()
                or manifest.stat().st_size > 4 * 1024 * 1024
            ):
                raise ValueError
            raw = manifest.read_bytes()
            metadata = json.loads(raw)
            commit = metadata.get("source_commit")
            return {
                "kind": "source-manifest",
                "manifest": manifest_name,
                "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                "source_commit": commit
                if isinstance(commit, str) and re.fullmatch("[a-f0-9]{40}", commit)
                else None,
                "review_only": True,
                "publication_authorized": False,
            }
        except (OSError, ValueError, AttributeError):
            return {"kind": "invalid-source-manifest", "manifest": manifest_name}
    check = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=ROOT, capture_output=True, text=True
    )
    if check.returncode or Path(check.stdout.strip()).resolve() != ROOT.resolve():
        return {"kind": "unversioned", "git_root_matches": False}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    )
    return {
        "kind": "git",
        "git_root_matches": True,
        "commit": head.stdout.strip() if head.returncode == 0 else None,
        "worktree_dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--browser", action="store_true", help="Also test installed Edge on two viewports"
    )
    parser.add_argument("--stage", choices=("S2", "S23", "S4", "S5"), default="S2")
    parser.add_argument(
        "--target",
        choices=("all", "desktop"),
        default="all",
        help="Desktop runs H5 and desktop browser only",
    )
    parser.add_argument(
        "--source-manifest",
        choices=("REVIEW-MANIFEST.json",),
        help="Verify an explicit review-only source archive without requiring its own Git index",
    )
    args = parser.parse_args()
    require_project_environment()
    source_before = source_snapshot(args.source_manifest)
    logs = ROOT / (
        ".local/logs/"
        + args.stage.lower()
        + ("-desktop" if args.target == "desktop" else "")
        + "-validation"
    )
    logs.mkdir(parents=True, exist_ok=True)
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    steps = [
        ("python-dependencies", [sys.executable, "-m", "pip", "check"]),
        ("python-lint", [sys.executable, "-m", "ruff", "check", "apps/server", "scripts", "tests"]),
        (
            "python-format",
            [sys.executable, "-m", "ruff", "format", "--check", "apps/server", "scripts", "tests"],
        ),
        (
            "python-tests",
            [
                sys.executable,
                "-m",
                "pytest",
                "--junitxml=" + (logs / "pytest.xml").relative_to(ROOT).as_posix(),
            ],
        ),
        ("backend-http", [sys.executable, "scripts/smoke_backend.py"]),
        ("model-http-dpapi", [sys.executable, "scripts/smoke_models.py"]),
        ("demand-http-restart", [sys.executable, "scripts/smoke_demands.py"]),
    ]
    steps += [
        ("frontend-" + name.replace(":", "-"), [npm, "--prefix", "apps/client", "run", name])
        for name in (
            ("lint", "typecheck", "test", "build:h5")
            if args.target == "desktop"
            else ("lint", "typecheck", "test", "build:h5", "build:weapp")
        )
    ]
    if args.browser:
        browser_command = [npm, "--prefix", "apps/client", "run", "test:browser"]
        if args.target == "desktop":
            browser_command += ["--", "--project=desktop-edge"]
        steps.append(("frontend-browser", browser_command))
    scan_command = [sys.executable, "scripts/scan_secrets.py"]
    if args.source_manifest:
        scan_command += ["--source-manifest", args.source_manifest]
    steps += [("secret-scan", scan_command)]
    results = []
    for name, command in steps:
        started = datetime.now(timezone.utc).isoformat()
        with (logs / (name + ".log")).open("w", encoding="utf-8") as log:
            result = subprocess.run(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=dict(
                    os.environ,
                    DSA_CLIENT_BUILD="staging",
                    DSA_VERIFY_DESKTOP="1" if args.target == "desktop" else "0",
                ),
            )
        row = {
            "name": name,
            "command": ["<project-python>" if v == sys.executable else v for v in command],
            "started_at": started,
            "exit_code": result.returncode,
            "log": (logs / (name + ".log")).relative_to(ROOT).as_posix(),
        }
        results.append(row)
        print(name + ": " + ("PASS" if result.returncode == 0 else "FAIL"), flush=True)
    report = {
        "stage": args.stage,
        "target": args.target,
        "other_platform_work_paused": args.target == "desktop",
        "source_snapshot": source_before,
        "source_snapshot_after": source_snapshot(args.source_manifest),
        "scope": "local engineering validation; not public deployment approval",
        "public_deployment_blocked": True,
        "passed": all(x["exit_code"] == 0 for x in results),
        "steps": results,
        "real_ai_or_product_apis_tested": False,
        "wechat_device_tested": False,
        "github_ci_executed": False,
        "edge_browser_requested": args.browser,
        "client_assets": ".local/s2-client (isolated staging)",
    }
    (logs / (args.stage.lower() + "-verification.json")).write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    raise SystemExit(not report["passed"])


if __name__ == "__main__":
    main()

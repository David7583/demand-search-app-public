"""Scan a project's Git index or an explicit source-archive manifest.

Neither mode grants release approval or claims to inspect complete Git history.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from export_simulated_market import EXPORT_RELATIVE_PATH, verify_export_bytes  # noqa: E402

MANIFEST_NAME = "REVIEW-MANIFEST.json"
PATTERNS = [
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
PRIVATE_DIRS = frozenset(
    {
        ".git",
        ".venv",
        ".local",
        "node_modules",
        "runtime",
        ".swc",
        ".taro",
        ".vite",
        "dist",
        "build",
        "coverage",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
    }
)

# Exact source-distribution roots retained for the two reviewed local forks.
# This exempts only these directory components, never their private children
# or any file from content inspection.
MAINTAINED_DIST_DIRS = frozenset(
    {
        "apps/client/tooling/taro-vite-runner/dist",
        "apps/client/tooling/taro-plugin-framework-react/dist",
    }
)


def _private_directory(name):
    return name.lower() in PRIVATE_DIRS or name.lower().endswith(".egg-info")


def _sensitive_file(name):
    lowered = name.lower()
    return (
        (lowered.startswith(".env") and lowered != ".env.example")
        or lowered == "project.private.config.json"
        or bool(re.search(r"\.(?:sqlite\w*|db(?:-.*)?|pem|key|pfx|p12|log)$", lowered))
    )


def _maintained_source_path(name):
    return any(name == prefix or name.startswith(prefix + "/") for prefix in MAINTAINED_DIST_DIRS)


def _private_path(name, *, is_directory=False):
    parts = PurePosixPath(name).parts
    for index, part in enumerate(parts):
        directory = is_directory or index < len(parts) - 1
        prefix = "/".join(parts[: index + 1])
        if _private_directory(part):
            if directory and part == "dist" and prefix in MAINTAINED_DIST_DIRS:
                continue
            return True
        if directory and _sensitive_file(part):
            return True
    return False


def _linked(path):
    return path.is_symlink() or path.is_junction()


def _result(counts, findings, mode):
    return {
        "files_scanned_by_scope": counts,
        "passed": not findings,
        "findings": findings,
        "history_scanned": False,
        "mode": mode,
        "release_authorized": False,
    }


def _inspect(name, data, scope, findings, counts):
    counts[scope] += 1
    if _private_path(name):
        findings.append({"path": name, "scope": scope, "reason": "private directory tracked"})
    if name == EXPORT_RELATIVE_PATH:
        try:
            # Validate these bytes, not the corresponding working-tree path.
            verify_export_bytes(data)
        except (ValueError, RuntimeError):
            findings.append(
                {"path": name, "scope": scope, "reason": "invalid synthetic seed database"}
            )
    elif _sensitive_file(PurePosixPath(name).name):
        findings.append({"path": name, "scope": scope, "reason": "sensitive file type"})
    if any(pattern.search(data) for pattern in PATTERNS):
        findings.append({"path": name, "scope": scope, "reason": "secret-like material"})


def scan(root: Path, source_manifest=None):
    root = Path(root).resolve()
    if source_manifest is not None:
        return _scan_archive(root, source_manifest)
    findings = []
    counts = {"index": 0, "worktree": 0}
    check = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True, text=True
    )
    if check.returncode != 0 or Path(check.stdout.strip()).resolve() != root:
        findings.append(
            {
                "scope": "index",
                "code": "GIT_ROOT_MISMATCH",
                "reason": "Use this project's own Git index or an explicit source manifest",
            }
        )
        return _result(counts, findings, "git")

    indexed = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=root)
    for entry in indexed.split(b"\0"):
        if not entry:
            continue
        meta, raw_name = entry.split(b"\t", 1)
        mode, sha, stage = meta.decode("ascii").split()
        name = raw_name.decode("utf-8")
        if mode != "100644" and mode != "100755":
            findings.append({"path": name, "scope": "index", "reason": "unsupported file mode"})
            continue
        if stage != "0":
            findings.append({"path": name, "scope": "index", "reason": "unmerged index"})
        data = subprocess.check_output(["git", "cat-file", "blob", sha], cwd=root)
        _inspect(name, data, "index", findings, counts)

    raw = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
    )
    for name in sorted(set(x.decode("utf-8") for x in raw.split(b"\0") if x)):
        path = root / name
        if _linked(path) or not path.resolve().is_relative_to(root):
            findings.append(
                {"path": name, "scope": "worktree", "reason": "external or linked path"}
            )
        elif path.is_file():
            _inspect(name, path.read_bytes(), "worktree", findings, counts)
    return _result(counts, findings, "git")


def _safe_source_path(value):
    if not isinstance(value, str) or not value or len(value) > 512:
        return False
    if any(c in value for c in '\\:<>"|?*') or any(
        ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value
    ):
        return False
    parts = value.split("/")
    if any(p in ("", ".", "..") or p.endswith((" ", ".")) for p in parts):
        return False
    reserved = r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?"
    return not any(re.fullmatch(reserved, p) for p in parts)


def _scan_archive(root, source_manifest):
    counts = {"manifest": 0}
    findings = []

    def reject(code, reason, name=None):
        row = {"scope": "manifest", "code": code, "reason": reason}
        if name is not None:
            row["path"] = name
        findings.append(row)

    if str(source_manifest) != MANIFEST_NAME:
        reject(
            "SOURCE_MANIFEST_INVALID", "The manifest must be REVIEW-MANIFEST.json at project root"
        )
        return _result(counts, findings, "source-manifest")
    manifest = root / MANIFEST_NAME
    try:
        if _linked(manifest) or not manifest.is_file() or manifest.stat().st_size > 4 * 1024 * 1024:
            raise ValueError
        document = json.loads(manifest.read_text(encoding="utf-8"))
        entries = document["files"]
        if not isinstance(entries, list) or not entries or len(entries) > 10000:
            raise ValueError
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        reject("SOURCE_MANIFEST_INVALID", "Missing, linked, oversized or invalid source manifest")
        return _result(counts, findings, "source-manifest")

    expected = {}
    folded = set()
    for entry in entries:
        if not isinstance(entry, dict) or not _safe_source_path(entry.get("path")):
            reject("SOURCE_PATH_UNSAFE", "Manifest contains a noncanonical relative path")
            continue
        name = entry["path"]
        if name.casefold() in folded:
            reject("SOURCE_PATH_UNSAFE", "Duplicate or case-colliding manifest path", name)
            continue
        folded.add(name.casefold())
        if name.casefold() == MANIFEST_NAME.casefold():
            reject("SOURCE_MANIFEST_INVALID", "The manifest cannot include itself", name)
            continue
        if _private_path(name) or (
            _sensitive_file(PurePosixPath(name).name) and name != EXPORT_RELATIVE_PATH
        ):
            reject(
                "SOURCE_PRIVATE_PATH", "Private or generated files cannot be source entries", name
            )
            continue
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest):
            reject("SOURCE_MANIFEST_INVALID", "A file must have a lowercase SHA-256 digest", name)
            continue
        expected[name] = digest

    # Validate metadata before opening any listed source, including private paths.
    if findings:
        return _result(counts, findings, "source-manifest")
    for name, digest in sorted(expected.items()):
        path = root / name
        ancestors = [path, *path.parents]
        if any(_linked(p) for p in ancestors if p != root and p.is_relative_to(root)):
            reject("SOURCE_SYMLINK", "Linked source paths are not allowed", name)
            continue
        if not path.resolve().is_relative_to(root):
            reject("SOURCE_PATH_UNSAFE", "Source path escapes project root", name)
            continue
        if not path.is_file():
            reject("SOURCE_MISSING_FILE", "Listed source file is missing", name)
            continue
        try:
            if path.stat().st_size > 64 * 1024 * 1024:
                reject("SOURCE_FILE_TOO_LARGE", "Source file exceeds the scan limit", name)
                continue
            data = path.read_bytes()
        except OSError:
            reject("SOURCE_FILE_UNREADABLE", "Source file could not be read", name)
            continue
        if hashlib.sha256(data).hexdigest() != digest:
            reject("SOURCE_FILE_HASH_MISMATCH", "Source file differs from the manifest", name)
        _inspect(name, data, "manifest", findings, counts)

    # This allowlist of generated directories is independent of .gitignore: a
    # modified ignore file cannot conceal extra source. Never recurse into data.
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            children = sorted(os.scandir(directory), key=lambda child: child.name)
        except OSError:
            reject("SOURCE_FILE_UNREADABLE", "Source directory could not be listed")
            continue
        for child in children:
            path = Path(child.path)
            name = path.relative_to(root).as_posix()
            if child.name == ".git" and not _maintained_source_path(name):
                continue
            if _linked(path):
                reject("SOURCE_SYMLINK", "Linked archive paths are not allowed", name)
                continue
            if child.is_dir(follow_symlinks=False):
                if _private_path(name, is_directory=True):
                    if _maintained_source_path(name):
                        reject(
                            "SOURCE_PRIVATE_PATH",
                            "Private directory inside maintained source; content was not read",
                            name,
                        )
                else:
                    pending.append(path)
                continue
            if name == MANIFEST_NAME or name in expected:
                continue
            if _sensitive_file(child.name):
                reject(
                    "SOURCE_PRIVATE_PATH", "Extra sensitive file exists; content was not read", name
                )
            elif child.name == ".DS_Store" or re.fullmatch(r".*\.py[cod]", child.name):
                continue
            else:
                reject("SOURCE_EXTRA_FILE", "Extra file is outside the reviewed manifest", name)
    return _result(counts, findings, "source-manifest")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-manifest", choices=(MANIFEST_NAME,))
    args = parser.parse_args()
    result = scan(ROOT, args.source_manifest)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(not result["passed"])

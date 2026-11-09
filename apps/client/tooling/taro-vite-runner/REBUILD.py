#!/usr/bin/env python3
"""Rebuild the exact maintained distribution from a verified npm archive.
No npm install, subprocess, global state, or active application write is performed.
Use a new --output directory; existing targets are refused.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent

def digest(data):
    return hashlib.sha256(data).hexdigest()

def safe_path(root, relative):
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Path escapes output directory")
    return target

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--archive", help="Optional existing original npm tgz")
    args = parser.parse_args()
    recipe = json.loads((HERE / "PATCHES.json").read_text(encoding="utf-8"))
    manifest = json.loads((HERE / "PATCH-MANIFEST.json").read_text(encoding="utf-8"))
    upstream = recipe["upstream"]
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError("Output must not exist; refusing overwrite")
    if args.archive:
        blob = Path(args.archive).read_bytes()
    else:
        with urllib.request.urlopen(upstream["tarball"], timeout=45) as response:
            blob = response.read()
    if digest(blob) != upstream["sha256"]:
        raise ValueError("Original archive SHA-256 mismatch")
    if upstream["integrity"] != "sha512-" + base64.b64encode(hashlib.sha512(blob).digest()).decode("ascii"):
        raise ValueError("Original archive SHA-512 mismatch")
    output.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        for member in archive.getmembers():
            parts = Path(member.name).parts
            if not parts or parts[0] != "package" or member.issym() or member.islnk():
                raise ValueError("Unexpected npm archive member")
            if len(parts) == 1:
                continue
            target = safe_path(output, Path(*parts[1:]))
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("Unreadable archive member")
                target.write_bytes(source.read())
            else:
                raise ValueError("Unsupported archive entry")
    for item in manifest["changed"]:
        if digest(safe_path(output, item["path"]).read_bytes()) != item["before_sha256"]:
            raise ValueError("Unexpected upstream input: " + item["path"])
    for operation in recipe["operations"]:
        path = safe_path(output, operation["path"])
        text = path.read_text(encoding="utf-8")
        if text.count(operation["before"]) != operation["count"]:
            raise ValueError("Patch match count differs: " + operation["path"])
        path.write_text(text.replace(operation["before"], operation["after"]), encoding="utf-8", newline="\n")
    for item in recipe["removed"]:
        path = safe_path(output, item["path"])
        if digest(path.read_bytes()) != item["sha256"]:
            raise ValueError("Removed file hash mismatch")
        path.unlink()
    for item in manifest["changed"]:
        if digest(safe_path(output, item["path"]).read_bytes()) != item["after_sha256"]:
            raise ValueError("Patched output differs: " + item["path"])
    if digest((output / "LICENSE").read_bytes()) != manifest["license_file_sha256"]:
        raise ValueError("Original MIT license differs")
    for name in ["PATCHES.json", "PATCH-MANIFEST.json", "maintenance.patch", "MAINTENANCE.md", "REBUILD.py"]:
        shutil.copyfile(HERE / name, output / name)
    if (HERE / "tests").exists():
        shutil.copytree(HERE / "tests", output / "tests")
    print(json.dumps({"output": str(output), "version": manifest["maintained_version"], "upstream_sha256": upstream["sha256"], "patched_files": len(manifest["changed"])}, indent=2))

if __name__ == "__main__":
    main()

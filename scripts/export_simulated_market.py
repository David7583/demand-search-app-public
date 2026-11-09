"""Export only the fixed synthetic seed. Never read or copy a runtime database."""

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from contextlib import closing
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/server/src"))

from demand_search.market_catalog import SEED_DATE, SEED_VERSION  # noqa: E402
from demand_search.simulated_market import (  # noqa: E402
    STORE_VERSION,
    canonical,
    expected_catalog,
)

EXPORT_RELATIVE_PATH = "data/simulated-market/market.synthetic.sqlite3"
EXPORT_SHA256 = "253dba7aa3cc2bc8ff2e7feaf2aa96ff18ba24bb4e8dfca276e72b76240e2602"
TABLE_SQL = {
    "market_metadata": "CREATE TABLE market_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)",
    "merchants": "CREATE TABLE merchants(id TEXT PRIMARY KEY,data_json TEXT NOT NULL)",
}


def _expected_rows():
    categories, merchants, digest = expected_catalog()
    metadata = {
        "store_version": STORE_VERSION,
        "seed_version": SEED_VERSION,
        "seed_date": SEED_DATE,
        "seed_sha256": digest,
        "categories_json": canonical(categories),
    }
    return metadata, [(merchant["id"], canonical(merchant)) for merchant in merchants]


@lru_cache(maxsize=1)
def _new_seed_bytes():
    """Fresh isolated SQLite, populated solely from deterministic source templates."""
    metadata, rows = _expected_rows()
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("PRAGMA page_size=4096")
        for statement in TABLE_SQL.values():
            db.execute(statement)
        db.executemany("INSERT INTO market_metadata VALUES (?,?)", sorted(metadata.items()))
        db.executemany("INSERT INTO merchants VALUES (?,?)", rows)
        db.commit()
        return db.serialize()


def verify_export_bytes(data):
    """Validate the actual supplied Git-index/archive bytes, with no filesystem DB access."""
    if not isinstance(data, bytes) or not 0 < len(data) <= 64 * 1024 * 1024:
        raise ValueError("Synthetic database size or representation is invalid")
    # The reviewed whole-file hash rejects deleted-cell remnants, unused-page secrets and
    # trailers without depending on the current SQLite serializer's binary layout.
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPORT_SHA256:
        raise ValueError("Database differs from the reviewed synthetic seed SHA-256")
    expected_metadata, expected_merchants = _expected_rows()
    with closing(sqlite3.connect(":memory:")) as db:
        db.deserialize(data)
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        objects = db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY name"
        ).fetchall()
        expected_objects = [
            ("table", name, name, statement) for name, statement in TABLE_SQL.items()
        ] + [("index", "sqlite_autoindex_" + name + "_1", name, None) for name in TABLE_SQL]
        if objects != sorted(expected_objects, key=lambda row: row[1]):
            raise ValueError("Only the two exact seed tables and primary-key indexes are allowed")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Synthetic database integrity check failed")
        if db.execute("PRAGMA freelist_count").fetchone()[0] != 0:
            raise ValueError("Synthetic database contains unused pages")
        metadata = dict(db.execute("SELECT key,value FROM market_metadata"))
        merchants = db.execute("SELECT id,data_json FROM merchants ORDER BY id").fetchall()
        if metadata != expected_metadata or merchants != expected_merchants:
            raise ValueError("Synthetic database content is not the complete fixed catalog")
        if (
            len(merchants) != 500
            or sum(len(json.loads(row[1])["offerings"]) for row in merchants) != 1500
        ):
            raise ValueError("Synthetic database coverage mismatch")
    return digest


def export_seed():
    target = ROOT / EXPORT_RELATIVE_PATH
    for part in [target, *target.parents]:
        if part == ROOT.parent:
            break
        if part.is_symlink() or part.is_junction():
            raise ValueError("Linked export destinations are not allowed")
    if not target.resolve().is_relative_to(ROOT):
        raise ValueError("Export destination escapes the project")
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.with_name(target.name + ".export-lock")
    try:
        with lock.open("x", encoding="ascii") as handle:
            handle.write("synthetic seed export in progress\n")
    except FileExistsError:
        raise ValueError(
            "Synthetic export is locked; inspect the existing lock before retrying"
        ) from None
    try:
        if target.exists():
            digest = verify_export_bytes(target.read_bytes())
            return {"path": EXPORT_RELATIVE_PATH, "sha256": digest, "reused": True}
        private_temp = ROOT / ".local"
        private_temp.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="synthetic-export-", dir=private_temp) as folder:
            candidate = Path(folder) / "fresh-seed.sqlite3"
            candidate.write_bytes(_new_seed_bytes())
            digest = verify_export_bytes(candidate.read_bytes())
            # Windows rename refuses an existing target, preventing accidental replacement.
            candidate.rename(target)
        return {"path": EXPORT_RELATIVE_PATH, "sha256": digest, "reused": False}
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify", action="store_true", help="Read-only verification of the export"
    )
    args = parser.parse_args()
    if args.verify:
        result = {
            "path": EXPORT_RELATIVE_PATH,
            "sha256": verify_export_bytes((ROOT / EXPORT_RELATIVE_PATH).read_bytes()),
            "verified": True,
        }
    else:
        result = export_seed()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()

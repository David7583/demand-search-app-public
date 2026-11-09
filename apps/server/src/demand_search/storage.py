"""Transactional project-local SQLite; migrations never reset user data."""

import sqlite3
from contextlib import closing, contextmanager
from uuid import uuid4

from .config import ROOT, Settings

LOCAL_OWNER = "local"


@contextmanager
def connect(settings: Settings):
    with closing(sqlite3.connect(settings.database, timeout=8)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        db.execute("PRAGMA busy_timeout=8000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise


def initialize(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with connect(settings) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL "
            "DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))"
        )
    for path in sorted((ROOT / "db/migrations").glob("*.sql")):
        version = int(path.name.split("_", 1)[0])
        with connect(settings) as db:
            # Acquire the writer lock before checking the version. Two startups
            # must never both decide to execute a non-idempotent migration.
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM schema_migrations WHERE version=?", (version,)).fetchone():
                continue
            statement = ""
            for char in path.read_text(encoding="utf-8"):
                statement += char
                if char == ";" and sqlite3.complete_statement(statement):
                    db.execute(statement)
                    statement = ""
            if statement.strip():
                db.execute(statement)
            db.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (version,))
    with connect(settings) as db:
        db.execute(
            "INSERT OR IGNORE INTO app_metadata(key,value) VALUES (?,?)",
            ("instance_id", str(uuid4())),
        )


def readiness(settings: Settings) -> bool:
    try:
        with closing(sqlite3.connect(f"{settings.database.as_uri()}?mode=ro", uri=True)) as db:
            versions = {row[0] for row in db.execute("SELECT version FROM schema_migrations")}
            expected = {
                int(p.name.split("_", 1)[0]) for p in (ROOT / "db/migrations").glob("*.sql")
            }
            return bool(expected) and expected.issubset(versions)
    except sqlite3.Error:
        return False

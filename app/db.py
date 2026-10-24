"""SQLite storage for a single-node, isolated operations lab.

Transactions use BEGIN IMMEDIATE so concurrent webhook deliveries are serialized.
This is intentionally NOT a multi-instance distributed database design.
"""
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3


def database_path() -> Path:
    return Path(os.environ.get("DATABASE_PATH", "data/incidents.sqlite"))


@contextmanager
def connection(*, write: bool = False):
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 15000")
    try:
        if write:
            db.execute("BEGIN IMMEDIATE")
        else:
            db.execute("BEGIN")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    with connection(write=True) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_event_id TEXT NOT NULL UNIQUE,
            host TEXT NOT NULL,
            trigger_id TEXT NOT NULL,
            title TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
                'OPEN', 'APPROVED', 'REPAIR_RECORDED', 'REPAIR_FAILED', 'RESOLVED')),
            approved_at TEXT,
            recovery_event_id TEXT,
            resolved_at TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL REFERENCES incidents(id),
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE TABLE IF NOT EXISTS recovery_events (
            event_id TEXT PRIMARY KEY,
            incident_id INTEGER NOT NULL REFERENCES incidents(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
        CREATE INDEX IF NOT EXISTS idx_incidents_host_trigger ON incidents(host, trigger_id, status);
        CREATE INDEX IF NOT EXISTS idx_audit_incident ON audit_events(incident_id);
        """)

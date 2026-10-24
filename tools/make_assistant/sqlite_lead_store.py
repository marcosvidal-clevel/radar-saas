"""Atomic SQLite idempotency ledger for offline lead intake. No network calls."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from commercial_pipeline import process_lead

class LeadStore:
    def __init__(self, db_path):
        self.db_path = str(Path(db_path))
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS lead_ledger (lead_key TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=15000")
            yield db
        finally:
            db.close()

    def claim(self, raw):
        """Reserve one accepted lead exactly once. Does not execute planned actions."""
        result = process_lead(raw, set())
        if result["status"] != "accepted":
            return result
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                cursor = db.execute("INSERT OR IGNORE INTO lead_ledger(lead_key) VALUES (?)", (result["key"],))
                db.commit()
            except BaseException:
                db.rollback()
                raise
        if cursor.rowcount == 0:
            return {"status": "duplicate", "key": result["key"], "actions": []}
        return result

    def count(self):
        with self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM lead_ledger").fetchone()[0]

"""Transactional outbox for commercial leads. Offline only; no external writes."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from commercial_pipeline import process_lead

class Outbox:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS leads (key TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_key TEXT NOT NULL, action TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                UNIQUE(lead_key, action),
                FOREIGN KEY(lead_key) REFERENCES leads(key))""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, raw):
        result = process_lead(raw, set())
        if result["status"] != "accepted":
            return result
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cur = db.execute("INSERT OR IGNORE INTO leads(key,payload) VALUES (?,?)",
                             (result["key"], json.dumps(raw)))
            if not cur.rowcount:
                return {"status":"duplicate","key":result["key"],"actions":[]}
            for action in result["actions"]:
                db.execute("INSERT INTO jobs(lead_key,action) VALUES (?,?)",
                           (result["key"], action["type"]))
        return result

    def pending(self, limit=100):
        with self.connect() as db:
            return db.execute("SELECT id,lead_key,action,attempts FROM jobs WHERE status='pending' ORDER BY id LIMIT ?",(limit,)).fetchall()

    def mark_success(self, job_id):
        with self.connect() as db:
            return db.execute("UPDATE jobs SET status='done' WHERE id=? AND status='pending'",(job_id,)).rowcount

    def mark_failure(self, job_id, error, max_attempts=5):
        with self.connect() as db:
            return db.execute("""UPDATE jobs SET attempts=attempts+1,
                last_error=?, status=CASE WHEN attempts+1>=? THEN 'failed' ELSE 'pending' END
                WHERE id=? AND status='pending'""",(str(error)[:250],max_attempts,job_id)).rowcount

    def stats(self):
        with self.connect() as db:
            return dict(db.execute("SELECT status,COUNT(*) FROM jobs GROUP BY status").fetchall())

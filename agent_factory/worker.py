"""Local worker with atomic claiming, explicit action allowlist and event log.

No network, deployment, emails or Make execution.
"""
import json
import sqlite3
from datetime import datetime, timezone
from .supervisor import Supervisor

ALLOWED_ACTIONS = frozenset({"audit", "validate", "document", "inspect"})
MAX_ATTEMPTS = 3

def now():
    return datetime.now(timezone.utc).isoformat()

class Worker:
    def __init__(self, database, handlers):
        self.supervisor = Supervisor(database)
        self.handlers = dict(handlers)
        with self.supervisor._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS agent_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL, kind TEXT NOT NULL,
                created_at TEXT NOT NULL, detail TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS agent_attempts (
                job_id TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0)""")

    def run_one(self):
        with self.supervisor._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id, agent, action, payload FROM jobs "
                "WHERE status='queued' ORDER BY created_at, id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            job_id, agent, action, payload = row
            if action not in ALLOWED_ACTIONS or (agent, action) not in self.handlers:
                db.execute("UPDATE jobs SET status='blocked', updated_at=? WHERE id=?",
                           (now(), job_id))
                self._event(db, job_id, "blocked", "No authorized handler")
                return {"id": job_id, "status": "blocked"}
            attempt = db.execute("SELECT count FROM agent_attempts WHERE job_id=?", (job_id,)).fetchone()
            count = (attempt[0] if attempt else 0) + 1
            db.execute("INSERT INTO agent_attempts(job_id,count) VALUES (?,?) "
                       "ON CONFLICT(job_id) DO UPDATE SET count=excluded.count", (job_id, count))
            db.execute("UPDATE jobs SET status='running', updated_at=? WHERE id=?",
                       (now(), job_id))
            self._event(db, job_id, "started", str(count))
        try:
            result = self.handlers[(agent, action)](json.loads(payload))
            # Ensure the output is JSON-serializable before writing.
            encoded = json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            # Do not persist exception messages: they can contain secrets.
            status = "failed" if count >= MAX_ATTEMPTS else "queued"
            with self.supervisor._connect() as db:
                db.execute("UPDATE jobs SET status=?, updated_at=? WHERE id=? AND status='running'",
                           (status, now(), job_id))
                self._event(db, job_id, "attempt_failed", type(exc).__name__)
            return {"id": job_id, "status": status}
        with self.supervisor._connect() as db:
            db.execute("UPDATE jobs SET status='completed', result=?, updated_at=? "
                       "WHERE id=? AND status='running'", (encoded, now(), job_id))
            self._event(db, job_id, "completed", "ok")
        return {"id": job_id, "status": "completed"}

    @staticmethod
    def _event(db, job_id, kind, detail):
        db.execute("INSERT INTO agent_events(job_id,kind,created_at,detail) VALUES (?,?,?,?)",
                   (job_id, kind, now(), detail))

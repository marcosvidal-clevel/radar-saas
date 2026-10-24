"""Supervisor local de la Fábrica de Agentes. Sin conexiones externas."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SENSITIVE = frozenset({'publish', 'send_email', 'delete', 'deploy', 'write_production'})

class Supervisor:
    def __init__(self, database):
        self.database = str(Path(database))
        with self._connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, agent TEXT NOT NULL, action TEXT NOT NULL,
                payload TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                result TEXT)''')

    def _connect(self):
        return sqlite3.connect(self.database)

    def submit(self, agent, action, payload):
        if not isinstance(payload, dict) or not agent or not action:
            raise ValueError('Se requieren agente, acción y datos válidos')
        canonical = json.dumps([agent, action, payload], sort_keys=True, ensure_ascii=False)
        job_id = hashlib.sha256(canonical.encode()).hexdigest()[:24]
        status = 'pending_approval' if action in SENSITIVE else 'queued'
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute('INSERT OR IGNORE INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, NULL)',
                       (job_id, agent, action, json.dumps(payload, ensure_ascii=False), status, now, now))
            row = db.execute('SELECT status FROM jobs WHERE id=?', (job_id,)).fetchone()
        return {'id': job_id, 'status': row[0]}

    def approve(self, job_id):
        with self._connect() as db:
            changed = db.execute("UPDATE jobs SET status='queued', updated_at=? WHERE id=? AND status='pending_approval'",
                                 (datetime.now(timezone.utc).isoformat(), job_id)).rowcount
        return changed == 1

    def complete(self, job_id, result):
        with self._connect() as db:
            changed = db.execute("UPDATE jobs SET status='completed', result=?, updated_at=? WHERE id=? AND status='queued'",
                                 (json.dumps(result, ensure_ascii=False), datetime.now(timezone.utc).isoformat(), job_id)).rowcount
        return changed == 1

    def list_jobs(self):
        with self._connect() as db:
            rows = db.execute('SELECT id, agent, action, status FROM jobs ORDER BY created_at').fetchall()
        return [dict(zip(('id', 'agent', 'action', 'status'), row)) for row in rows]

"""Offline tenant-scoped idempotency registry for RADAR opportunities.

Stores only external key and RADAR ID, no contact details. No API calls.
"""
import sqlite3
from contextlib import contextmanager

class RadarMappingLedger:
    def __init__(self, path):
        self.path=str(path)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS radar_mapping (
                organization_id INTEGER NOT NULL,
                external_key TEXT NOT NULL,
                opportunity_id INTEGER NOT NULL,
                PRIMARY KEY (organization_id, external_key),
                UNIQUE (organization_id, opportunity_id)
            )""")

    @contextmanager
    def _db(self):
        db=sqlite3.connect(self.path, timeout=15)
        try:
            db.execute("PRAGMA busy_timeout=15000")
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _validate(organization_id, external_key):
        if type(organization_id) is not int or organization_id <= 0:
            raise ValueError("Invalid organization")
        if not isinstance(external_key,str) or not external_key.strip():
            raise ValueError("Invalid external key")

    def get(self, organization_id, external_key):
        self._validate(organization_id,external_key)
        with self._db() as db:
            row=db.execute("SELECT opportunity_id FROM radar_mapping WHERE organization_id=? AND external_key=?",
                           (organization_id,external_key)).fetchone()
            return row[0] if row else None

    def register(self, organization_id, external_key, opportunity_id):
        self._validate(organization_id,external_key)
        if type(opportunity_id) is not int or opportunity_id<=0:
            raise ValueError("Invalid opportunity ID")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing=db.execute("SELECT opportunity_id FROM radar_mapping WHERE organization_id=? AND external_key=?",
                                (organization_id,external_key)).fetchone()
            if existing:
                if existing[0] != opportunity_id:
                    raise ValueError("Conflicting RADAR mapping")
                return False
            db.execute("INSERT INTO radar_mapping VALUES (?,?,?)",
                       (organization_id,external_key,opportunity_id))
            return True

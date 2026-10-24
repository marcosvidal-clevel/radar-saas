"""Exclusive SQLite job leasing; offline coordination, no external writes."""
import secrets
import time
from commercial_outbox import Outbox
from delivery_contracts import prepare_delivery, verify_receipt

class LeasedOutbox(Outbox):
    def __init__(self, path):
        super().__init__(path)
        with self.connect() as db:
            cols = {r[1] for r in db.execute("PRAGMA table_info(jobs)")}
            for name, kind in [("lease_token","TEXT"),("lease_until","REAL"),("next_attempt_at","REAL NOT NULL DEFAULT 0")]:
                if name not in cols:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {kind}")

    def mark_success(self, job_id):
        raise RuntimeError('Use acknowledge() with a verified receipt and lease token')

    def mark_failure(self, job_id, error, max_attempts=5):
        raise RuntimeError('Use reject() with the active lease token')

    def claim_next(self, lease_seconds=60, now=None):
        if lease_seconds <= 0: raise ValueError("lease_seconds must be positive")
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT j.id,j.lead_key,j.action,j.attempts FROM jobs j
                WHERE ((j.status='pending' AND j.next_attempt_at<=?) OR
                       (j.status='leased' AND j.lease_until<=?))
                AND (j.action='append_lead' OR (j.action='notify_internal' AND EXISTS (
                    SELECT 1 FROM jobs p WHERE p.lead_key=j.lead_key
                    AND p.action='append_lead' AND p.status='done')))
                ORDER BY j.id LIMIT 1""",(now,now)).fetchone()
            if row is None: return None
            token=secrets.token_hex(16)
            db.execute("UPDATE jobs SET status=?,lease_token=?,lease_until=? WHERE id=?",
                       ("leased",token,now+lease_seconds,row[0]))
            return {"id":row[0],"key":row[1],"action":row[2],"attempts":row[3],"token":token}

    def acknowledge(self, job_id, token, receipt, now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT id,lead_key,action,attempts FROM jobs WHERE id=? AND status=? AND lease_token=? AND lease_until>?",
                           (job_id,"leased",token,now)).fetchone()
            if not row or not verify_receipt(prepare_delivery(row),receipt): return False
            return db.execute("UPDATE jobs SET status='done',lease_token=NULL,lease_until=NULL WHERE id=?",(job_id,)).rowcount==1

    def reject(self, job_id, token, error, now=None, max_attempts=5, base_delay=30):
        now=time.time() if now is None else now
        if max_attempts<1 or base_delay<0: raise ValueError("Invalid retry policy")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT attempts FROM jobs WHERE id=? AND status=? AND lease_token=? AND lease_until>?",
                           (job_id,"leased",token,now)).fetchone()
            if not row: return False
            attempts=row[0]+1
            status="failed" if attempts>=max_attempts else "pending"
            delay=min(base_delay*2**(attempts-1),3600)
            db.execute("""UPDATE jobs SET attempts=?,status=?,last_error=?,next_attempt_at=?,
                          lease_token=NULL,lease_until=NULL WHERE id=?""",
                       (attempts,status,str(error)[:250],now+delay,job_id))
            return True

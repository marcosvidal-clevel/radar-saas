"""Read-only scheduling policy for outbox jobs; does not execute or acknowledge."""
from delivery_contracts import prepare_delivery

def eligible_jobs(store, limit=100):
    """Notify only after append_lead was acknowledged as done.
    Pending append jobs may be offered; no external side effects.
    """
    with store.connect() as db:
        rows = db.execute("""
            SELECT j.id,j.lead_key,j.action,j.attempts
            FROM jobs j
            WHERE j.status='pending'
              AND (j.action='append_lead' OR
                   (j.action='notify_internal' AND EXISTS (
                     SELECT 1 FROM jobs p
                     WHERE p.lead_key=j.lead_key AND p.action='append_lead'
                       AND p.status='done')))
            ORDER BY j.id LIMIT ?
        """,(limit,)).fetchall()
    return [prepare_delivery(row) for row in rows]

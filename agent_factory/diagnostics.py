"""Read-only agent factory diagnostics. No external side effects."""
from .supervisor import Supervisor
from .worker import Worker

def health_report(database):
    worker = Worker(database, {})
    jobs = worker.supervisor.list_jobs()
    counts = {}
    for job in jobs:
        counts[job["status"]] = counts.get(job["status"], 0) + 1
    with worker.supervisor._connect() as db:
        events = db.execute("SELECT kind, COUNT(*) FROM agent_events GROUP BY kind").fetchall()
    return {"total_jobs": len(jobs), "statuses": counts, "events": dict(events)}

def export_safe_report(database):
    """Returns only aggregate counts, never payloads, credentials or personal data."""
    return health_report(database)

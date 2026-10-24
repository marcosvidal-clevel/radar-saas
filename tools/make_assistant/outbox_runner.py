"""Safe offline outbox runner. Dry-run only; never calls Make, Sheets or RADAR."""
from commercial_outbox import Outbox

class DryRunExecutor:
    def execute(self, action, key):
        if action not in {"append_lead", "notify_internal"}:
            raise ValueError("Unsupported action")
        return {"simulated": True, "action": action, "key": key}

def preview_pending(store, executor=None, limit=100):
    """Preview jobs without marking them done; simulation cannot acknowledge delivery."""
    executor = executor or DryRunExecutor()
    previews = []
    for job_id, key, action, attempts in store.pending(limit=limit):
        previews.append({"job_id": job_id, "attempts": attempts, **executor.execute(action, key)})
    return previews

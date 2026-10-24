"""Safe Make inventory adapter: offline-first, read-only and no credentials in reports."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Scenario:
    scenario_id: int
    name: str
    active: bool

def summarize_inventory(rows):
    """Validate a normalized inventory without contacting Make."""
    if not isinstance(rows, list):
        raise ValueError("Invalid inventory")
    seen = set()
    summary = {"total": 0, "active": 0, "inactive": 0}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid scenario")
        sid = row.get("id")
        active = row.get("isActive")
        if type(sid) is not int or sid <= 0 or sid in seen or type(active) is not bool:
            raise ValueError("Invalid or duplicate scenario")
        seen.add(sid)
        summary["total"] += 1
        summary["active" if active else "inactive"] += 1
    return summary

def make_inventory_handler(inventory_provider):
    """Dependency-injected provider. Production API access remains separately gated."""
    def handle(payload):
        if payload.get("mode") != "read_only":
            raise ValueError("Only read-only Make inventory is supported")
        return summarize_inventory(inventory_provider())
    return handle

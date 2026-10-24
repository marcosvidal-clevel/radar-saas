"""Strict offline delivery contracts; no network or side effects."""
from dataclasses import dataclass

ALLOWED_ACTIONS = frozenset({"append_lead", "notify_internal"})
@dataclass(frozen=True)
class Delivery:
    job_id: int
    lead_key: str
    action: str
    idempotency_key: str

def prepare_delivery(job):
    job_id, lead_key, action, attempts = job
    if not isinstance(job_id, int) or job_id <= 0:
        raise ValueError("Invalid job id")
    if action not in ALLOWED_ACTIONS:
        raise ValueError("Unsupported action")
    if not isinstance(lead_key, str) or len(lead_key) != 64 or any(c not in "0123456789abcdef" for c in lead_key):
        raise ValueError("Invalid lead key")
    return Delivery(job_id, lead_key, action, f"{lead_key}:{action}")

def verify_receipt(delivery, receipt):
    """Only a matching explicit external acknowledgement can be accepted."""
    return (isinstance(receipt, dict)
            and receipt.get("status") == "confirmed"
            and receipt.get("idempotency_key") == delivery.idempotency_key
            and isinstance(receipt.get("external_id"), str)
            and bool(receipt["external_id"].strip()))

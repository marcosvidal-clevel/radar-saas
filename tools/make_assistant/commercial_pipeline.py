"""Offline commercial lead processing: deterministic, idempotent, no network calls."""
import hashlib
import re
from dataclasses import dataclass

EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

@dataclass(frozen=True)
class Lead:
    email: str
    name: str = ""
    source: str = "web"
    consent: bool = False

def normalize_email(email):
    return (email or "").strip().casefold()

def lead_key(email):
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()

def process_lead(raw, known_keys):
    """Returns instructions only; does not send, persist or mutate external services."""
    if not isinstance(raw, dict):
        return {"status": "rejected", "reason": "invalid_payload", "actions": []}
    email = normalize_email(raw.get("email"))
    if not EMAIL.fullmatch(email):
        return {"status": "rejected", "reason": "invalid_email", "actions": []}
    key = lead_key(email)
    if key in known_keys:
        return {"status": "duplicate", "key": key, "actions": []}
    if raw.get("consent") is not True:
        return {"status": "review", "reason": "consent_not_confirmed", "key": key, "actions": []}
    lead = Lead(email=email, name=str(raw.get("name") or "").strip()[:200],
                source=str(raw.get("source") or "web")[:60], consent=True)
    return {"status": "accepted", "key": key,
            "actions": [
                {"type": "append_lead", "data": {"email": lead.email, "name": lead.name, "source": lead.source, "key": key}},
                {"type": "notify_internal", "key": key}
            ]}

def batch_plan(records, known_keys=()):
    keys = set(known_keys)
    results = []
    for raw in records:
        result = process_lead(raw, keys)
        results.append(result)
        if result["status"] == "accepted":
            keys.add(result["key"])
    return results

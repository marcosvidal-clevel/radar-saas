"""Offline RADAR lead adapter. No database writes or network calls."""
from commercial_pipeline import batch_plan

def prepare_radar_import(records, known_keys=()):
    """Produce RADAR-compatible candidate commercial opportunity payloads.
    These are drafts; model field names and org authorization require integration checks.
    """
    results = batch_plan(records, known_keys)
    drafts = []
    for index, result in enumerate(results):
        if result["status"] != "accepted":
            continue
        source = records[index]
        drafts.append({
            "external_key": result["key"],
            "origin": "consulta_entrante",
            "channel": "web" if source.get("source", "web") == "web" else "otro",
            "status": "nueva",
            "contact_email": result["actions"][0]["data"]["email"],
            "contact_name": result["actions"][0]["data"]["name"],
            "requires_organization_mapping": True,
        })
    return {"decisions": results, "radar_drafts": drafts}

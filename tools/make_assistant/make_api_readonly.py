"""Read-only Make API client. Never logs tokens or writes scenarios."""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ALLOWED_HOSTS = {"eu1.make.com", "eu2.make.com", "us1.make.com", "us2.make.com"}
class MakeAPIError(RuntimeError): pass

def get_scenario(scenario_id, *, token=None, host=None, opener=urlopen):
    token = token or os.getenv("MAKE_API_TOKEN")
    host = host or os.getenv("MAKE_API_HOST")
    if not token:
        raise MakeAPIError("MAKE_API_TOKEN not configured")
    if host not in ALLOWED_HOSTS:
        raise MakeAPIError("Invalid Make API host")
    if not str(scenario_id).isdigit():
        raise MakeAPIError("Invalid scenario id")
    req = Request(
        f"https://{host}/api/v2/scenarios/{scenario_id}",
        headers={"Authorization": f"Token {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with opener(req, timeout=20) as response:
            data = json.load(response)
    except (HTTPError, URLError, ValueError) as exc:
        raise MakeAPIError(f"Make read failed ({type(exc).__name__})") from None
    if not isinstance(data, dict):
        raise MakeAPIError("Unexpected response")
    return data

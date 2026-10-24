"""Small read-only Make API adapter. No scenario execution or mutations."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


class MakeAPIError(Exception):
    """Safe error: never includes response bodies or the API credential."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the Authorization header to a redirect destination.
        return None


class MakeClient:
    ZONES = frozenset({"us1", "us2", "eu1", "eu2"})
    MAX_BYTES = 2 * 1024 * 1024
    PAGE_SIZE = 100
    MAX_PAGES = 20

    def __init__(self, token, *, zone="us1", team_id=576170):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9._~-]{16,512}", token):
            raise MakeAPIError("MAKE_API_TOKEN ausente o inválido.")
        if zone not in self.ZONES:
            raise MakeAPIError("Zona Make no admitida.")
        if type(team_id) is not int or team_id < 1:
            raise MakeAPIError("Equipo Make inválido.")
        self._token = token
        self.zone = zone
        self.team_id = team_id
        self._opener = build_opener(_NoRedirect())

    def _get(self, path, params=None):
        url = f"https://{self.zone}.make.com/api/v2/{path}"
        if params:
            url += "?" + urlencode(params, doseq=True)
        req = Request(url, headers={
            "Authorization": f"Token {self._token}",
            "Accept": "application/json",
        }, method="GET")
        try:
            with self._opener.open(req, timeout=20) as response:
                if response.status != 200:
                    raise MakeAPIError("Make no confirmó la lectura (HTTP inesperado).")
                raw = response.read(self.MAX_BYTES + 1)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            messages = {
                401: "Make rechazó la autenticación (HTTP 401).",
                403: "Make denegó acceso: revisar permisos, organización o plan (HTTP 403).",
                429: "Make limitó las consultas (HTTP 429); reintentar más tarde.",
            }
            raise MakeAPIError(messages.get(status, f"Make devolvió HTTP {status}.")) from None
        except (URLError, TimeoutError, OSError):
            raise MakeAPIError("No se pudo contactar con Make; autenticación no verificada.") from None
        if len(raw) > self.MAX_BYTES:
            raise MakeAPIError("Respuesta Make demasiado grande; lectura incompleta.")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            raise MakeAPIError("Make devolvió una respuesta JSON inválida.") from None
        if not isinstance(data, dict):
            raise MakeAPIError("Make devolvió una estructura inesperada.")
        return data

    def list_scenarios(self):
        """Fetch every page, reject mixed-team or incomplete responses."""
        scenarios = []
        seen = set()
        for page in range(self.MAX_PAGES):
            data = self._get("scenarios", {
                "teamId": self.team_id,
                "type": "scenario",
                "cols[]": ["id", "name", "teamId", "isActive", "dlqCount"],
                "pg[limit]": self.PAGE_SIZE,
                "pg[offset]": page * self.PAGE_SIZE,
                "pg[sortBy]": "id",
                "pg[sortDir]": "asc",
            })
            rows = data.get("scenarios")
            if not isinstance(rows, list) or len(rows) > self.PAGE_SIZE:
                raise MakeAPIError("Inventario Make inválido o incompleto.")
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or type(row.get("id")) is not int
                    or row["id"] <= 0
                    or row["id"] in seen
                    or row.get("teamId") != self.team_id
                    or not isinstance(row.get("name"), str)
                    or type(row.get("isActive")) is not bool
                ):
                    raise MakeAPIError("Inventario Make inconsistente; revisar equipo o paginación.")
                seen.add(row["id"])
                # Avoid returning author emails, blueprint bodies or other data.
                scenarios.append({key: row.get(key) for key in (
                    "id", "name", "teamId", "isActive", "dlqCount",
                )})
            if len(rows) < self.PAGE_SIZE:
                return scenarios
        raise MakeAPIError("Límite de páginas alcanzado; inventario incompleto.")

    def verify(self, expected_ids=(4996755, 4996645)):
        rows = self.list_scenarios()
        missing = sorted(set(expected_ids) - {row["id"] for row in rows})
        if missing:
            raise MakeAPIError("API accesible, pero faltan escenarios esperados: " + ", ".join(map(str, missing)))
        return {
            "authentication": "verified",
            "verification": "GET scenarios succeeded; expected scenarios present",
            "mode": "read_only",
            "zone": self.zone,
            "team_id": self.team_id,
            "scenarios": rows,
        }

"""Verify Make authentication without executing or modifying scenarios."""

import json
import os
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from core.make_api import MakeAPIError, MakeClient


class Command(BaseCommand):
    help = "Verifica API Make y consulta escenarios; solo lectura, sin cambios en RADAR."

    def handle(self, *args, **options):
        try:
            team_id = int(os.environ.get("MAKE_TEAM_ID", "576170"))
            client = MakeClient(
                os.environ.get("MAKE_API_TOKEN", ""),
                zone=os.environ.get("MAKE_ZONE", "us1"),
                team_id=team_id,
            )
            result = client.verify()
        except ValueError:
            raise CommandError("MAKE_TEAM_ID debe ser un entero positivo.") from None
        except MakeAPIError as exc:
            raise CommandError(str(exc)) from None
        result["verified_at"] = datetime.now(timezone.utc).isoformat()
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))

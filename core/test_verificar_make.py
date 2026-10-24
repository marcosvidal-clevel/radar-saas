"""Command tests with synthetic environment and no network or database."""

import io
import json
import unittest
from unittest.mock import patch

from django.core.management.base import CommandError

from core.make_api import MakeAPIError
from core.management.commands.verificar_make import Command


class VerifyCommandTests(unittest.TestCase):
    def test_missing_secret_fails_without_network(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(CommandError, "MAKE_API_TOKEN"):
                Command(stdout=io.StringIO()).handle()

    def test_invalid_team_fails(self):
        with patch.dict("os.environ", {"MAKE_TEAM_ID": "bad"}, clear=True):
            with self.assertRaisesRegex(CommandError, "MAKE_TEAM_ID"):
                Command(stdout=io.StringIO()).handle()

    def test_success_outputs_timestamp_only_after_api_verification(self):
        stream = io.StringIO()
        with patch("core.management.commands.verificar_make.MakeClient") as client:
            client.return_value.verify.return_value = {"authentication": "verified"}
            Command(stdout=stream).handle()
        result = json.loads(stream.getvalue())
        self.assertEqual(result["authentication"], "verified")
        self.assertIn("verified_at", result)

    def test_api_error_has_no_success_output(self):
        stream = io.StringIO()
        with patch("core.management.commands.verificar_make.MakeClient") as client:
            client.return_value.verify.side_effect = MakeAPIError("HTTP 401")
            with self.assertRaisesRegex(CommandError, "401"):
                Command(stdout=stream).handle()
        self.assertEqual(stream.getvalue(), "")

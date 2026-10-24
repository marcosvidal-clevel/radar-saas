"""Offline contract tests. No real tokens, Make calls or database required."""

import io
import json
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from core.make_api import MakeAPIError, MakeClient, _NoRedirect


def scenario(pk, **extra):
    return {"id": pk, "name": "Escenario sintético", "teamId": 576170,
            "isActive": False, "dlqCount": 0, **extra}


class MakeClientTests(unittest.TestCase):
    def setUp(self):
        self.client = MakeClient("synthetic-token-for-offline-tests")
        self.client._opener = Mock()

    def response(self, value):
        response = Mock()
        response.status = 200
        response.read.return_value = json.dumps(value).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_success_checks_both_expected_scenarios(self):
        self.client._opener.open.return_value = self.response({
            "scenarios": [scenario(4996755), scenario(4996645)]})
        result = self.client.verify()
        self.assertEqual(result["authentication"], "verified")
        req = self.client._opener.open.call_args.args[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertTrue(req.full_url.startswith("https://us1.make.com/api/v2/scenarios?"))
        self.assertEqual(req.get_header("Authorization"), "Token synthetic-token-for-offline-tests")
        self.assertNotIn("synthetic-token", json.dumps(result))

    def test_missing_token_fails_before_network(self):
        with self.assertRaises(MakeAPIError):
            MakeClient("")

    def test_rejects_header_injection(self):
        with self.assertRaises(MakeAPIError):
            MakeClient("invalid-token\r\nOther: bad")

    def test_untrusted_zone_rejected(self):
        with self.assertRaises(MakeAPIError):
            MakeClient("synthetic-token-offline", zone="evil.example")

    def test_auth_errors_do_not_leak_response_or_secret(self):
        for code in [401, 403, 429, 500, 302]:
            with self.subTest(code=code):
                self.client._opener.open.side_effect = HTTPError(
                    "https://example.test", code, "secret", {}, io.BytesIO(b"secret"))
                with self.assertRaises(MakeAPIError) as caught:
                    self.client.verify()
                self.assertIn(str(code), str(caught.exception))
                self.assertNotIn("secret", str(caught.exception))

    def test_network_failure_is_not_authentication(self):
        self.client._opener.open.side_effect = URLError("secret")
        with self.assertRaisesRegex(MakeAPIError, "no verificada"):
            self.client.verify()

    def test_missing_expected_scenario_does_not_claim_success(self):
        self.client._opener.open.return_value = self.response({"scenarios": [scenario(4996755)]})
        with self.assertRaisesRegex(MakeAPIError, "4996645"):
            self.client.verify()

    def test_other_team_and_unknown_active_status_rejected(self):
        for row in [scenario(1, teamId=123), scenario(1, isActive=None), scenario(True)]:
            self.client._opener.open.return_value = self.response({"scenarios": [row]})
            with self.assertRaises(MakeAPIError):
                self.client.list_scenarios()

    def test_pagination_fetches_second_page(self):
        self.client.PAGE_SIZE = 1
        self.client._opener.open.side_effect = [
            self.response({"scenarios": [scenario(1)]}),
            self.response({"scenarios": [scenario(2)]}),
            self.response({"scenarios": []}),
        ]
        self.assertEqual(len(self.client.list_scenarios()), 2)
        req = self.client._opener.open.call_args_list[1].args[0]
        self.assertIn("pg%5Boffset%5D=1", req.full_url)

    def test_repeated_page_fails_closed(self):
        self.client.PAGE_SIZE = 1
        self.client._opener.open.return_value = self.response({"scenarios": [scenario(1)]})
        with self.assertRaisesRegex(MakeAPIError, "inconsistente"):
            self.client.list_scenarios()

    def test_page_limit_not_silently_truncated(self):
        self.client.MAX_PAGES = 1
        self.client.PAGE_SIZE = 1
        self.client._opener.open.return_value = self.response({"scenarios": [scenario(1)]})
        with self.assertRaisesRegex(MakeAPIError, "incompleto"):
            self.client.list_scenarios()

    def test_invalid_and_oversize_responses_rejected(self):
        for raw in [b"not json", b"[]", b"{}", b"x" * (self.client.MAX_BYTES + 1)]:
            response = self.response({})
            response.read.return_value = raw
            self.client._opener.open.return_value = response
            with self.assertRaises(MakeAPIError):
                self.client.list_scenarios()

    def test_redirects_disabled(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example"))


if __name__ == "__main__":
    unittest.main()

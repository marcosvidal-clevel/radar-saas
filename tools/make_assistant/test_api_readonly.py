import io
import json
import unittest
from make_api_readonly import get_scenario, MakeAPIError

class FakeResponse:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, *args): return b'{"scenario":{"id":4996755}}'

class APITests(unittest.TestCase):
    def test_get_only_and_token(self):
        def opener(req, timeout):
            self.assertEqual(req.get_method(), "GET")
            self.assertEqual(req.get_header("Authorization"), "Token dummy")
            self.assertEqual(timeout, 20)
            return FakeResponse()
        self.assertEqual(get_scenario(4996755, token="dummy", host="eu1.make.com", opener=opener)["scenario"]["id"],4996755)
    def test_reject_host(self):
        with self.assertRaises(MakeAPIError):
            get_scenario(1, token="dummy", host="evil.example")
    def test_reject_id(self):
        with self.assertRaises(MakeAPIError):
            get_scenario("../x", token="dummy", host="eu1.make.com")
    def test_missing_token(self):
        with self.assertRaises(MakeAPIError):
            get_scenario(1, token="", host="eu1.make.com")

if __name__ == "__main__":
    unittest.main()

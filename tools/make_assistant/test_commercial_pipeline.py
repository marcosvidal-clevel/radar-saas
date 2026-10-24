import unittest
from commercial_pipeline import batch_plan, lead_key, process_lead

class CommercialTests(unittest.TestCase):
    def test_normalized_deduplication(self):
        self.assertEqual(lead_key("  ABC@EXAMPLE.COM "),lead_key("abc@example.com"))
    def test_accept_with_consent(self):
        r=process_lead({"email":"a@example.com","consent":True},set())
        self.assertEqual(r["status"],"accepted")
        self.assertEqual([a["type"] for a in r["actions"]],["append_lead","notify_internal"])
    def test_duplicate(self):
        r=process_lead({"email":"a@example.com","consent":True},{lead_key("a@example.com")})
        self.assertEqual(r["status"],"duplicate")
    def test_invalid_email(self):
        self.assertEqual(process_lead({"email":"bad","consent":True},set())["status"],"rejected")
    def test_missing_consent(self):
        self.assertEqual(process_lead({"email":"a@example.com"},set())["status"],"review")
    def test_batch_same_email(self):
        r=batch_plan([{"email":"a@example.com","consent":True},{"email":"A@EXAMPLE.COM","consent":True}])
        self.assertEqual([x["status"] for x in r],["accepted","duplicate"])
    def test_invalid_payload(self):
        self.assertEqual(process_lead(None,set())["status"],"rejected")

if __name__=="__main__":
    unittest.main()

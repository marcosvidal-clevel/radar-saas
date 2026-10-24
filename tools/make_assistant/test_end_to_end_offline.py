"""Offline end-to-end contract tests: synthetic data, no API calls."""
import tempfile
import unittest
from pathlib import Path
from commercial_outbox import Outbox
from delivery_scheduler import eligible_jobs
from delivery_contracts import verify_receipt
from outbox_runner import preview_pending

class OfflineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Outbox(Path(self.temp.name) / "leads.db")
        self.raw = {"email":"synthetic@example.invalid", "name":"Test", "consent":True}

    def test_ordered_delivery(self):
        self.assertEqual(self.store.enqueue(self.raw)["status"], "accepted")
        self.assertEqual([x.action for x in eligible_jobs(self.store)], ["append_lead"])
        first = eligible_jobs(self.store)[0]
        self.assertFalse(verify_receipt(first, {"simulated":True}))
        self.assertTrue(verify_receipt(first, {
            "status":"confirmed", "idempotency_key":first.idempotency_key,
            "external_id":"synthetic-row-1"}))
        self.assertEqual(self.store.mark_success(first.job_id),1)
        self.assertEqual([x.action for x in eligible_jobs(self.store)], ["notify_internal"])
        second = eligible_jobs(self.store)[0]
        self.assertEqual(self.store.mark_success(second.job_id),1)
        self.assertEqual(self.store.stats().get("done"),2)

    def test_preview_does_not_complete(self):
        self.store.enqueue(self.raw)
        self.assertEqual(len(preview_pending(self.store)),2)
        self.assertEqual(self.store.stats().get("done",0),0)

    def test_failed_persistence_blocks_notification(self):
        self.store.enqueue(self.raw)
        job = eligible_jobs(self.store)[0]
        for _ in range(5):
            self.store.mark_failure(job.job_id, "synthetic failure")
        self.assertEqual(eligible_jobs(self.store),[])
        self.assertEqual(self.store.stats().get("failed"),1)

    def test_duplicate_does_not_create_more_jobs(self):
        self.store.enqueue(self.raw)
        self.assertEqual(self.store.enqueue(self.raw)["status"],"duplicate")
        self.assertEqual(len(self.store.pending()),2)

if __name__=="__main__":
    unittest.main()

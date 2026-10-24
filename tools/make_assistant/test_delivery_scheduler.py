import tempfile
import unittest
from pathlib import Path
from commercial_outbox import Outbox
from delivery_scheduler import eligible_jobs

class DeliverySchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Outbox(Path(self.tmp.name)/"db.sqlite")
        self.db.enqueue({"email":"test@example.com","consent":True})
    def test_notify_blocked_until_persisted(self):
        self.assertEqual([x.action for x in eligible_jobs(self.db)],["append_lead"])
    def test_notify_allowed_after_ack(self):
        job=self.db.pending()[0]
        self.db.mark_success(job[0])
        self.assertEqual([x.action for x in eligible_jobs(self.db)],["notify_internal"])
    def test_failed_append_never_notifies(self):
        job=self.db.pending()[0]
        for _ in range(5): self.db.mark_failure(job[0],"simulated")
        self.assertEqual(eligible_jobs(self.db),[])
    def test_preview_does_not_acknowledge(self):
        self.assertEqual(len(eligible_jobs(self.db)),1)
        self.assertEqual(self.db.stats().get("done",0),0)
if __name__=="__main__": unittest.main()

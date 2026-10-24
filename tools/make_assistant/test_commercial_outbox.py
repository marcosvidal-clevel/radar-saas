import tempfile
import unittest
from pathlib import Path
from commercial_outbox import Outbox

class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Outbox(Path(self.tmp.name)/"outbox.db")
        self.raw={"email":"contact@example.com","consent":True}
    def test_two_jobs_and_dedup(self):
        self.assertEqual(self.db.enqueue(self.raw)["status"],"accepted")
        self.assertEqual(self.db.enqueue(self.raw)["status"],"duplicate")
        self.assertEqual(len(self.db.pending()),2)
    def test_success(self):
        self.db.enqueue(self.raw)
        job=self.db.pending()[0]
        self.assertEqual(self.db.mark_success(job[0]),1)
        self.assertEqual(self.db.stats()["done"],1)
    def test_retry_and_dead_letter(self):
        self.db.enqueue(self.raw)
        job=self.db.pending()[0]
        for _ in range(5):
            self.db.mark_failure(job[0],"synthetic error")
        self.assertEqual(self.db.stats()["failed"],1)
        self.assertEqual(len(self.db.pending()),1)
    def test_no_consent_no_jobs(self):
        self.assertEqual(self.db.enqueue({"email":"a@example.com"})["status"],"review")
        self.assertEqual(self.db.pending(),[])
if __name__=="__main__": unittest.main()

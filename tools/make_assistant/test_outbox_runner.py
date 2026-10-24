import tempfile
import unittest
from pathlib import Path
from commercial_outbox import Outbox
from outbox_runner import preview_pending, DryRunExecutor

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=Outbox(Path(self.tmp.name)/"db.sqlite")
    def test_preview_never_acknowledges(self):
        self.store.enqueue({"email":"a@example.com","consent":True})
        self.assertEqual(len(preview_pending(self.store)),2)
        self.assertEqual(len(self.store.pending()),2)
    def test_reject_unknown_action(self):
        with self.assertRaises(ValueError):
            DryRunExecutor().execute("delete_scenario","key")
    def test_no_jobs(self):
        self.assertEqual(preview_pending(self.store),[])
if __name__=="__main__": unittest.main()

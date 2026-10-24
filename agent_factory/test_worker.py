import tempfile
import unittest
from pathlib import Path
from .worker import Worker
from .supervisor import Supervisor

class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "agent.sqlite"

    def tearDown(self):
        self.temp.cleanup()

    def test_success_and_no_reexecution(self):
        calls = []
        w = Worker(self.path, {("make", "audit"): lambda p: calls.append(p) or {"ok": True}})
        job = w.supervisor.submit("make", "audit", {"scenario": 123})
        self.assertEqual(w.run_one()["status"], "completed")
        self.assertIsNone(w.run_one())
        self.assertEqual(len(calls), 1)
        self.assertEqual(w.supervisor.submit("make", "audit", {"scenario": 123})["id"], job["id"])

    def test_sensitive_job_never_runs(self):
        w = Worker(self.path, {("web", "publish"): lambda p: {"ok": True}})
        job = w.supervisor.submit("web", "publish", {})
        self.assertIsNone(w.run_one())
        self.assertTrue(w.supervisor.approve(job["id"]))
        self.assertEqual(w.run_one()["status"], "blocked")

    def test_retry_limit(self):
        def fail(_):
            raise RuntimeError("secret should not be stored")
        w = Worker(self.path, {("make", "audit"): fail})
        w.supervisor.submit("make", "audit", {})
        self.assertEqual([w.run_one()["status"] for _ in range(3)],
                         ["queued", "queued", "failed"])
        self.assertIsNone(w.run_one())
        with w.supervisor._connect() as db:
            details = str(db.execute("SELECT detail FROM agent_events").fetchall())
        self.assertNotIn("secret should not be stored", details)

import tempfile
import unittest
from pathlib import Path
from .diagnostics import health_report
from .supervisor import Supervisor

class DiagnosticsTests(unittest.TestCase):
    def test_aggregate_report(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "jobs.sqlite"
            s = Supervisor(path)
            s.submit("make", "audit", {"private": "never export"})
            s.submit("web", "publish", {"secret": "never export"})
            result = health_report(path)
            self.assertEqual(result["total_jobs"], 2)
            self.assertEqual(result["statuses"]["queued"], 1)
            self.assertEqual(result["statuses"]["pending_approval"], 1)
            self.assertNotIn("never export", str(result))

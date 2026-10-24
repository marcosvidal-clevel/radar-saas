import tempfile
import unittest
from pathlib import Path
from .supervisor import Supervisor

class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.s = Supervisor(Path(self.temp.name) / 'jobs.sqlite')

    def tearDown(self):
        self.temp.cleanup()

    def test_deduplication(self):
        a = self.s.submit('make', 'audit', {'scenario': 1})
        b = self.s.submit('make', 'audit', {'scenario': 1})
        self.assertEqual(a, b)
        self.assertEqual(len(self.s.list_jobs()), 1)

    def test_sensitive_action_requires_approval(self):
        job = self.s.submit('web', 'publish', {'version': 30})
        self.assertEqual(job['status'], 'pending_approval')
        self.assertFalse(self.s.complete(job['id'], {'ok': True}))
        self.assertTrue(self.s.approve(job['id']))
        self.assertTrue(self.s.complete(job['id'], {'ok': True}))

    def test_completed_cannot_repeat(self):
        job = self.s.submit('radar', 'audit', {})
        self.assertTrue(self.s.complete(job['id'], {'ok': True}))
        self.assertFalse(self.s.complete(job['id'], {'ok': True}))

import tempfile
import unittest
from pathlib import Path
from leased_outbox import LeasedOutbox

class LeaseSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=LeasedOutbox(Path(self.tmp.name)/'db.sqlite')
        self.store.enqueue({'email':'test@example.com','consent':True})
    def test_no_unverified_success(self):
        job=self.store.claim_next(now=100)
        with self.assertRaises(RuntimeError): self.store.mark_success(job['id'])
        self.assertEqual(self.store.stats()['leased'],1)
    def test_no_unowned_failure(self):
        job=self.store.claim_next(now=100)
        with self.assertRaises(RuntimeError): self.store.mark_failure(job['id'],'failure')
        self.assertEqual(self.store.stats()['leased'],1)
    def test_valid_ack_still_works(self):
        job=self.store.claim_next(now=100)
        receipt={'status':'confirmed','idempotency_key':job['key']+':'+job['action'],'external_id':'synthetic-row'}
        self.assertTrue(self.store.acknowledge(job['id'],job['token'],receipt,now=101))
        self.assertEqual(self.store.stats()['done'],1)

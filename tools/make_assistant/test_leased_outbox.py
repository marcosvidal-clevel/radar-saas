import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from leased_outbox import LeasedOutbox

class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.db=LeasedOutbox(Path(self.tmp.name)/"db.sqlite")
        self.db.enqueue({"email":"synthetic@example.com","consent":True})
    def receipt(self,job):
        return {"status":"confirmed","idempotency_key":job["key"]+":"+job["action"],"external_id":"synthetic-123"}
    def test_exclusive_concurrent_claim(self):
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(lambda _:self.db.claim_next(now=100),range(12)))
        self.assertEqual(sum(x is not None for x in results),1)
    def test_expired_lease_and_stale_token(self):
        a=self.db.claim_next(now=100,lease_seconds=10)
        b=self.db.claim_next(now=111)
        self.assertNotEqual(a["token"],b["token"])
        self.assertFalse(self.db.acknowledge(a["id"],a["token"],self.receipt(a),now=112))
        self.assertTrue(self.db.acknowledge(b["id"],b["token"],self.receipt(b),now=112))
    def test_notification_depends_on_receipt(self):
        a=self.db.claim_next(now=100)
        self.assertIsNone(self.db.claim_next(now=100))
        self.assertFalse(self.db.acknowledge(a["id"],a["token"],{"simulated":True},now=101))
        self.assertTrue(self.db.acknowledge(a["id"],a["token"],self.receipt(a),now=101))
        self.assertEqual(self.db.claim_next(now=102)["action"],"notify_internal")
    def test_backoff(self):
        a=self.db.claim_next(now=100)
        self.assertTrue(self.db.reject(a["id"],a["token"],"temporary",now=101,base_delay=30))
        self.assertIsNone(self.db.claim_next(now=130))
        b=self.db.claim_next(now=131)
        self.assertEqual(b["attempts"],1)
        self.assertTrue(self.db.reject(b["id"],b["token"],"temporary",now=132,base_delay=30))
        self.assertIsNone(self.db.claim_next(now=191))
        self.assertIsNotNone(self.db.claim_next(now=192))
    def test_invalid_receipt(self):
        a=self.db.claim_next(now=100)
        self.assertFalse(self.db.acknowledge(a["id"],a["token"],{"status":"confirmed","idempotency_key":"wrong","external_id":"x"},now=101))
        self.assertEqual(self.db.stats()["leased"],1)
if __name__=="__main__": unittest.main()

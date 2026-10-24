import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from sqlite_lead_store import LeadStore

class SQLiteLeadStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = LeadStore(Path(self.tmp.name) / "leads.sqlite")
    def test_single_claim(self):
        self.assertEqual(self.store.claim({"email":"hello@example.com","consent":True})["status"],"accepted")
        self.assertEqual(self.store.count(),1)
    def test_repeat_is_duplicate(self):
        raw={"email":"hello@example.com","consent":True}
        self.assertEqual(self.store.claim(raw)["status"],"accepted")
        self.assertEqual(self.store.claim(raw)["status"],"duplicate")
        self.assertEqual(self.store.count(),1)
    def test_concurrent_claim(self):
        raw={"email":"hello@example.com","consent":True}
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(self.store.claim,[raw]*30))
        self.assertEqual(sum(x["status"]=="accepted" for x in results),1)
        self.assertEqual(sum(x["status"]=="duplicate" for x in results),29)
        self.assertEqual(self.store.count(),1)
    def test_no_consent_not_stored(self):
        self.assertEqual(self.store.claim({"email":"hello@example.com"})["status"],"review")
        self.assertEqual(self.store.count(),0)

if __name__=="__main__": unittest.main()

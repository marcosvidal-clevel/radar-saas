import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from radar_mapping_ledger import RadarMappingLedger

class MappingLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=RadarMappingLedger(Path(self.temp.name)/"mapping.sqlite")
    def test_register_and_get(self):
        self.assertTrue(self.db.register(1,"lead:a",10))
        self.assertEqual(self.db.get(1,"lead:a"),10)
        self.assertFalse(self.db.register(1,"lead:a",10))
    def test_organization_isolation(self):
        self.db.register(1,"lead:a",10)
        self.assertIsNone(self.db.get(2,"lead:a"))
        self.assertTrue(self.db.register(2,"lead:a",20))
    def test_conflict(self):
        self.db.register(1,"lead:a",10)
        with self.assertRaises(ValueError): self.db.register(1,"lead:a",11)
    def test_invalid_organization(self):
        with self.assertRaises(ValueError): self.db.register(True,"lead:a",10)
    def test_concurrent_same_mapping(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.db.register(1,"lead:a",10),range(16)))
        self.assertEqual(sum(results),1)
if __name__=="__main__": unittest.main()

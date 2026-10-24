import unittest
from .make_inventory import summarize_inventory, make_inventory_handler

class MakeInventoryTests(unittest.TestCase):
    def test_summary(self):
        rows = [{"id": 1, "isActive": True}, {"id": 2, "isActive": False}]
        self.assertEqual(summarize_inventory(rows), {"total": 2, "active": 1, "inactive": 1})

    def test_rejects_duplicates(self):
        with self.assertRaises(ValueError):
            summarize_inventory([{"id": 1, "isActive": True}, {"id": 1, "isActive": False}])

    def test_read_only_mode(self):
        handler = make_inventory_handler(lambda: [{"id": 4, "isActive": False}])
        self.assertEqual(handler({"mode": "read_only"})["inactive"], 1)
        with self.assertRaises(ValueError):
            handler({"mode": "execute"})

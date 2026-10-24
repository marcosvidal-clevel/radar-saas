"""Static contract tests; no Django database or network required."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).parent

class RadarServiceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(ROOT/'radar_transaction_service.py').read_text()
        cls.tree=ast.parse(cls.source)
    def test_service_parses(self):
        self.assertTrue(any(isinstance(n,ast.FunctionDef) and n.name=='import_web_opportunity' for n in ast.walk(self.tree)))
    def test_atomic_transaction(self):
        self.assertIn('transaction.atomic()',self.source)
    def test_org_lock(self):
        self.assertIn('select_for_update()',self.source)
    def test_authentication(self):
        self.assertIn('is_authenticated',self.source)
        self.assertIn('Membresia.objects.filter',self.source)
    def test_idempotency(self):
        self.assertIn('clave_externa=external_key',self.source)
        self.assertIn('if existing:',self.source)
    def test_validation(self):
        self.assertIn('opportunity.full_clean()',self.source)
        self.assertIn('mapping.full_clean()',self.source)

if __name__=='__main__': unittest.main()

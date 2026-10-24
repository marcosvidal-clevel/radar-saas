import unittest
from delivery_contracts import prepare_delivery, verify_receipt

class DeliveryContractTests(unittest.TestCase):
    def setUp(self):
        self.job=(1, "a"*64, "append_lead", 0)
    def test_contract(self):
        d=prepare_delivery(self.job)
        self.assertEqual(d.idempotency_key,"a"*64+":append_lead")
    def test_confirmed_receipt(self):
        d=prepare_delivery(self.job)
        self.assertTrue(verify_receipt(d,{"status":"confirmed","idempotency_key":d.idempotency_key,"external_id":"row-123"}))
    def test_wrong_receipt(self):
        d=prepare_delivery(self.job)
        self.assertFalse(verify_receipt(d,{"status":"confirmed","idempotency_key":"wrong","external_id":"row-123"}))
    def test_dry_run_not_receipt(self):
        d=prepare_delivery(self.job)
        self.assertFalse(verify_receipt(d,{"simulated":True,"action":"append_lead"}))
    def test_unsupported(self):
        with self.assertRaises(ValueError):
            prepare_delivery((1,"a"*64,"delete_scenario",0))
    def test_invalid_key(self):
        with self.assertRaises(ValueError):
            prepare_delivery((1,"not-a-hash","append_lead",0))

if __name__=="__main__": unittest.main()

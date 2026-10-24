import unittest
from integration_adapters import sheets_row, radar_opportunity
class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.job=(1,'a'*64,'append_lead',0)
        self.lead={'email':' Person@Example.COM ', 'consent':True,'name':'Example'}
    def test_sheets(self):
        row=sheets_row(self.job,self.lead)
        self.assertEqual(row['email'],'person@example.com')
        self.assertEqual(row['idempotency_key'],'a'*64+':append_lead')
    def test_radar(self):
        result=radar_opportunity(self.job,self.lead,9)
        self.assertEqual(result['organization_id'],9)
        self.assertEqual(result['origin'],'consulta_entrante')
    def test_consent(self):
        with self.assertRaises(ValueError): sheets_row(self.job,{'email':'a@example.com'})
    def test_action(self):
        with self.assertRaises(ValueError): sheets_row((1,'a'*64,'notify_internal',0),self.lead)
    def test_org(self):
        with self.assertRaises(ValueError): radar_opportunity(self.job,self.lead,0)
if __name__=='__main__': unittest.main()

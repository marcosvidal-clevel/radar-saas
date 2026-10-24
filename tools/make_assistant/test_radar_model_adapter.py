import unittest
from radar_model_adapter import opportunity_fields,external_reference
class RadarModelAdapterTests(unittest.TestCase):
    def setUp(self):
        self.job=(1,'b'*64,'append_lead',0)
        self.lead={'email':'  Person@Example.com  ','consent':True,'name':'Persona','need':'Búsqueda de gerente'}
    def test_matches_real_field_names(self):
        result=opportunity_fields(self.job,self.lead,3)
        self.assertEqual(result['organizacion_id'],3)
        self.assertEqual(result['email_consultante'],'person@example.com')
        self.assertEqual(result['origen'],'consulta_entrante')
        self.assertEqual(result['canal'],'web')
        self.assertEqual(result['necesidad'],'Búsqueda de gerente')
        self.assertNotIn('external_key',result)
    def test_reference_separate(self):
        self.assertEqual(external_reference(self.job),'b'*64+':append_lead')
    def test_reject_missing_consent(self):
        with self.assertRaises(ValueError): opportunity_fields(self.job,{'email':'x@example.com'},3)
    def test_reject_invalid_org(self):
        with self.assertRaises(ValueError): opportunity_fields(self.job,self.lead,False)
    def test_reject_wrong_action(self):
        with self.assertRaises(ValueError): opportunity_fields((1,'b'*64,'notify_internal',0),self.lead,3)
if __name__=='__main__': unittest.main()

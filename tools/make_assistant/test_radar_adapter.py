import unittest
from radar_adapter import prepare_radar_import

class RadarAdapterTests(unittest.TestCase):
    def test_draft(self):
        r=prepare_radar_import([{"email":"test@example.com","consent":True}])
        self.assertEqual(len(r["radar_drafts"]),1)
        self.assertEqual(r["radar_drafts"][0]["origin"],"consulta_entrante")
        self.assertTrue(r["radar_drafts"][0]["requires_organization_mapping"])
    def test_no_draft_without_consent(self):
        self.assertEqual(prepare_radar_import([{"email":"test@example.com"}])["radar_drafts"],[])
    def test_no_duplicate_drafts(self):
        r=prepare_radar_import([{"email":"test@example.com","consent":True},{"email":"TEST@example.com","consent":True}])
        self.assertEqual(len(r["radar_drafts"]),1)
if __name__=="__main__": unittest.main()

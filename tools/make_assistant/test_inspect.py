import unittest
from make_inspector import inspect_blueprint

class InspectTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(inspect_blueprint({"flow":[{"id":1,"module":"x"}]})["valid"])
    def test_duplicate(self):
        self.assertFalse(inspect_blueprint({"flow":[{"id":1,"module":"x"},{"id":1,"module":"y"}]})["valid"])
    def test_nested_duplicate(self):
        data={"flow":[{"id":1,"module":"router","routes":[{"flow":[{"id":1,"module":"x"}]}]}]}
        self.assertFalse(inspect_blueprint(data)["valid"])
    def test_bad_route(self):
        self.assertFalse(inspect_blueprint({"flow":[{"id":1,"module":"router","routes":[{}]}]})["valid"])
    def test_missing_module(self):
        self.assertFalse(inspect_blueprint({"flow":[{"id":1}]})["valid"])
    def test_missing_flow(self):
        self.assertFalse(inspect_blueprint({})["valid"])
    def test_no_id_warning(self):
        report=inspect_blueprint({"flow":[{"module":"x"}]})
        self.assertTrue(report["valid"])
        self.assertTrue(report["warnings"])

if __name__ == "__main__":
    unittest.main()

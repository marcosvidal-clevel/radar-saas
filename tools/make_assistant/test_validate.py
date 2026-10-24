import unittest
from validate import validate_plan, validate_blueprint

class ValidatorTests(unittest.TestCase):
    def test_plan_valid(self):
        self.assertEqual(validate_plan({"name":"test","steps":[{"action":"start"}]}), [])
    def test_plan_invalid(self):
        self.assertTrue(validate_plan({"steps":[]}))
    def test_blueprint_valid(self):
        self.assertEqual(validate_blueprint({"flow":[{"module":"builtin:BasicRouter"}]}), [])
    def test_blueprint_invalid(self):
        self.assertTrue(validate_blueprint({"flow":[{}]}))

if __name__ == "__main__":
    unittest.main()

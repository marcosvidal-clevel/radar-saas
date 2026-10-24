import unittest
from plan_compiler import compile_plan, PlanError
from diagnostics import diagnose

class CompilerTests(unittest.TestCase):
    def test_compile(self):
        result = compile_plan({"name":"Leads","steps":[{"action":"webhook"},{"action":"google_sheets_add_row"},{"action":"email_notify"}]})
        self.assertEqual(len(result["flow"]),3)
        self.assertTrue(result["_draft"]["not_import_ready"])
    def test_unsupported(self):
        with self.assertRaises(PlanError):
            compile_plan({"name":"X","steps":[{"action":"execute_arbitrary_code"}]})
    def test_empty(self):
        with self.assertRaises(PlanError):
            compile_plan({"name":"X","steps":[]})
    def test_diagnostics(self):
        result = diagnose({"flow":[{"id":1,"module":"gateway:CustomWebHook"}]})
        self.assertEqual(result["module_count"],1)
        self.assertTrue(result["valid_structure"])

if __name__ == "__main__":
    unittest.main()

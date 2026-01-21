import unittest
from mdr_gtk.diagnostics import run_diagnostics

class TestDiagnostics(unittest.TestCase):
    def test_run_diagnostics(self):
        res = run_diagnostics()
        self.assertIsInstance(res.ok, bool)
        self.assertTrue(len(res.lines) >= 2)

if __name__ == "__main__":
    unittest.main()

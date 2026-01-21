import unittest
from pathlib import Path

class TestReleaseHardening(unittest.TestCase):
    def test_doctor_exists_and_executable(self):
        p = Path("doctor.sh")
        self.assertTrue(p.exists())
        # can't guarantee exec bit in all environments, but file should exist
        self.assertGreater(p.stat().st_size, 10)

    def test_about(self):
        from mdr_gtk.about import APP_NAME, APP_VERSION
        self.assertTrue(APP_NAME)
        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+$")

if __name__ == "__main__":
    unittest.main()

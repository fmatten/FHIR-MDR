import unittest
from pathlib import Path

class TestG31Packaging(unittest.TestCase):
    def test_packaging_skeleton(self):
        self.assertTrue(Path("packaging/README.md").exists())
        self.assertTrue(Path("packaging/windows/README.md").exists())
        self.assertTrue(Path("packaging/macos/README.md").exists())
        self.assertTrue(Path("doctor.py").exists())

if __name__ == "__main__":
    unittest.main()

import unittest

class TestAppImports(unittest.TestCase):
    def test_app_imports(self):
        try:
            import gi  # noqa
        except Exception:
            self.skipTest("PyGObject (gi) not available in this test environment")
        import mdr_gtk.app  # noqa

if __name__ == "__main__":
    unittest.main()

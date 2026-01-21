import os
import unittest

class TestGUISmoke(unittest.TestCase):
    def test_imports(self):
        # Skip if PyGObject/GTK not available (common in headless CI)
        try:
            import gi  # noqa
        except Exception:
            self.skipTest("PyGObject not available")
        import mdr_gtk.ui  # noqa
        import mdr_gtk.app  # noqa

    def test_window_constructs_if_display_available(self):
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            self.skipTest("No DISPLAY/WAYLAND_DISPLAY; skipping GTK window instantiation test")

        try:
            import gi
            gi.require_version("Gtk", "4.0")
            from gi.repository import Gtk
        except Exception:
            self.skipTest("PyGObject/GTK4 not available")

        from mdr_gtk.ui import MDRWindow

        app = Gtk.Application(application_id="org.example.mdrsmoke")
        app.register()

        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            dbp = str(Path(td) / "t.sqlite")
            win = MDRWindow(app, dbp, use_adwaita=False)
            self.assertIsNotNone(win)
            win.close()

if __name__ == "__main__":
    unittest.main()

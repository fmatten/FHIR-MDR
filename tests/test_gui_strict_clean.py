import os
import unittest

class TestGUIStrictClean(unittest.TestCase):
    def test_gui_strict_clean(self):
        try:
            import gi
            gi.require_version("Gtk", "4.0")
            from gi.repository import Gtk
        except Exception as e:
            self.skipTest(f"GTK not available: {e}")

        # optional headless check (Linux):
        if os.name != "nt" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            self.skipTest("No DISPLAY/WAYLAND_DISPLAY (headless)")

        from mdr_gtk.app import MDRApp
        # App minimal starten/stoppen ohne Klick-Automation
        app = MDRApp()
        app.register(None)
        app.activate()
        for w in list(app.get_windows()):
            w.close()
        app.quit()

        # Kein Gtk.events_pending() in GTK4 – lieber GLib main context iterieren,
        # aber auch das optional/defensiv.

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio

try:
    gi.require_version("Adw", "1")
    from gi.repository import Adw  # type: ignore
    HAVE_ADW = True
except Exception:
    HAVE_ADW = False
    Adw = None  # type: ignore

from mdr_gtk.ui import MDRWindow
from mdr_gtk.diagnostics import run_diagnostics, REQUIRED_ACTIONS


class MDRApp(Gtk.Application):
    def __init__(self, db_path: str):
        super().__init__(application_id="org.example.mdrgtk")
        self.db_path = db_path

    def do_startup(self):
        Gtk.Application.do_startup(self)
        # App actions for menu
        for name in ["export_json","import_json","export_csv","export_skos",
            "open_db", "new_db",
            "import_fhir_bundle","import_fhir_package",
            "export_fhir_bundle_json","export_fhir_bundle_xml"
        ]:
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", self._on_action)
            self.add_action(act)

    def _on_action(self, action, _param):
        # forward to active window
        win = self.get_active_window()
        try:
            if not win:
                return
            name = action.get_name()
            if name == "export_json":
                win.export_json_dialog()
            elif name == "import_json":
                win.import_json_dialog()
            elif name == "export_csv":
                win.export_csv_dialog()
            elif name == "open_db":
                win.open_db_dialog()
            elif name == "new_db":
                win.new_db_dialog()

            elif name == "import_fhir_bundle":
                win.import_fhir_bundle_dialog()
            elif name == "import_fhir_package":
                win.import_fhir_package_dialog()
            elif name == "export_fhir_bundle_json":
                win.export_fhir_bundle_json_dialog()
            elif name == "export_fhir_bundle_xml":
                win.export_fhir_bundle_xml_dialog()

            elif name == "export_skos":
                win.export_skos_dialog()

        except Exception as e:
            try:
                win._log(f"Action {action.get_name()} failed: {e}")
                win._show_error_dialog("Action failed", str(e))
            except Exception:
                print(f"Action {action.get_name()} failed: {e}")
    def do_activate(self):
        win = MDRWindow(self, self.db_path, use_adwaita=HAVE_ADW)
        win.present()
        # Startup self-check (prints to console and log panel)
        diag = run_diagnostics()
        for line in diag.lines:
            try:
                win._log("[self-check] " + line)
            except Exception:
                print("[self-check] " + line)

        missing = [a for a in REQUIRED_ACTIONS if self.lookup_action(a) is None]
        if missing:
            msg = "FAIL: missing actions: " + ", ".join(missing)
            try:
                win._log("[self-check] " + msg)
            except Exception:
                print("[self-check] " + msg)
        else:
            try:
                win._log("[self-check] OK: all actions registered")
            except Exception:
                print("[self-check] OK: all actions registered")

def run_app(db_path: str) -> None:
    app = MDRApp(db_path)
    app.run([])

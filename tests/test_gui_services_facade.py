import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from unittest import TestCase, mock

from mdr_gtk.gui_services import GUIServiceFacade


class TestGUIServiceFacade(TestCase):
    """GUI service facade tests should not leak SQLite connections.

    Windows is particularly strict about open handles, but we also want to avoid
    noisy ResourceWarnings on Linux. Therefore each test owns its own in-memory
    connection and closes it deterministically.
    """

    def test_import_bundle_json_file_routes_and_ensures_schema(self):
        with closing(sqlite3.connect(":memory:")) as conn:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "bundle.json"
                p.write_text('{"resourceType":"Bundle","type":"collection","entry":[]}', encoding="utf-8")

                with mock.patch("mdr_gtk.gui_services.ensure_schema_applied") as ens, \
                     mock.patch("mdr_gtk.gui_services.import_fhir_bundle_json") as imp:
                    svc = GUIServiceFacade(conn)
                    svc.import_fhir_bundle_json_file(str(p))
                    ens.assert_called_once()
                    imp.assert_called_once()

    def test_import_package_routes_and_ensures_schema(self):
        with closing(sqlite3.connect(":memory:")) as conn:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "pkg.tgz"
                p.write_bytes(b"not-a-real-tgz")

                with mock.patch("mdr_gtk.gui_services.ensure_schema_applied") as ens, \
                     mock.patch("mdr_gtk.gui_services.import_fhir_package") as imp:
                    svc = GUIServiceFacade(conn)
                    svc.import_fhir_package_file(str(p))
                    ens.assert_called_once()
                    imp.assert_called_once()

    def test_export_selected_routes_and_ensures_schema(self):
        with closing(sqlite3.connect(":memory:")) as conn:
            with mock.patch("mdr_gtk.gui_services.ensure_schema_applied") as ens, \
                 mock.patch("mdr_gtk.gui_services.export_selected_bundle_json") as exj, \
                 mock.patch("mdr_gtk.gui_services.export_selected_bundle_xml") as exx:
                svc = GUIServiceFacade(conn)
                svc.export_selected_json(["cur1"], "out.json")
                svc.export_selected_xml(["cur1"], "out.xml")
                self.assertGreaterEqual(ens.call_count, 2)
                exj.assert_called_once()
                exx.assert_called_once()

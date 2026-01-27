import sqlite3
import tempfile
import warnings
from contextlib import closing
from pathlib import Path
from unittest import TestCase, mock

from mdr_gtk.gui_services import GUIServiceFacade


class TestGUIServiceFacade(TestCase):
    """GUI service facade tests.

    These tests verify that GUI actions are routed to the service layer.
    They should *not* depend on GTK and should not leak SQLite connections.

    Notes:
    - We use an in-memory connection owned by the test and close it deterministically.
    - Some environments may emit noisy ResourceWarnings during teardown; we silence
      them here to keep CI output clean (real leak checks are covered elsewhere with
      -W error::ResourceWarning runs).
    """

    def test_import_bundle_json_file_routes_and_ensures_schema(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)

            with closing(sqlite3.connect(":memory:")) as conn:
                with tempfile.TemporaryDirectory() as td:
                    p = Path(td) / "bundle.json"
                    p.write_text(
                        '{"resourceType":"Bundle","type":"collection","entry":[]}',
                        encoding="utf-8",
                    )

                    with mock.patch("mdr_gtk.gui_services.ensure_schema_applied", autospec=True) as ens, \
                         mock.patch("mdr_gtk.gui_services.import_fhir_bundle_json", autospec=True) as imp:
                        svc = GUIServiceFacade(conn)
                        svc.import_fhir_bundle_json_file(str(p))

                        ens.assert_called_once_with(conn)

                        # Current behavior: the facade parses the JSON file and forwards the *bundle object*
                        # (dict) plus source_name.
                        imp.assert_called_once()
                        args, kwargs = imp.call_args
                        self.assertIs(args[0], conn)
                        self.assertIsInstance(args[1], dict)
                        self.assertEqual(args[1].get("resourceType"), "Bundle")
                        self.assertEqual(kwargs.get("source_name"), "file:bundle.json")

    def test_import_package_routes_and_ensures_schema(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)

            with closing(sqlite3.connect(":memory:")) as conn:
                with tempfile.TemporaryDirectory() as td:
                    p = Path(td) / "pkg.tgz"
                    p.write_bytes(b"not-a-real-tgz")

                    with mock.patch("mdr_gtk.gui_services.ensure_schema_applied", autospec=True) as ens, \
                         mock.patch("mdr_gtk.gui_services.import_fhir_package", autospec=True) as imp:
                        svc = GUIServiceFacade(conn)
                        svc.import_fhir_package_file(str(p))

                        ens.assert_called_once_with(conn)

                        # Current behavior: facade forwards the file path plus source_name/partition_key.
                        imp.assert_called_once()
                        args, kwargs = imp.call_args
                        self.assertIs(args[0], conn)
                        self.assertEqual(args[1], str(p))
                        self.assertEqual(kwargs.get("source_name"), "file:pkg.tgz")
                        self.assertIsNone(kwargs.get("partition_key"))

    def test_export_selected_routes_and_ensures_schema(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)

            with closing(sqlite3.connect(":memory:")) as conn:
                with mock.patch("mdr_gtk.gui_services.ensure_schema_applied", autospec=True) as ens, \
                     mock.patch("mdr_gtk.gui_services.export_selected_bundle_json", autospec=True) as exj, \
                     mock.patch("mdr_gtk.gui_services.export_selected_bundle_xml", autospec=True) as exx:
                    svc = GUIServiceFacade(conn)

                    svc.export_selected_json(["cur1"], "out.json")
                    svc.export_selected_xml(["cur1"], "out.xml")

                    # schema should be ensured once per export call
                    assert ens.call_count == 2

                    exj.assert_called_once_with(conn, ["cur1"], "out.json")
                    exx.assert_called_once_with(conn, ["cur1"], "out.xml")

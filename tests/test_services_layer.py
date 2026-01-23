import json
import tempfile
import unittest
from pathlib import Path

from mdr_gtk.services import ensure_schema_applied, MDRServices
from mdr_gtk.db import connect


class TestServicesLayer(unittest.TestCase):
    def test_ensure_schema_applies_to_empty_db(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mdr.sqlite"
            conn = connect(str(db_path))
            try:
                ensure_schema_applied(conn)
                # core + fhir table exist
                row1 = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='registrable_item'").fetchone()
                row2 = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fhir_ingest_run'").fetchone()
                self.assertIsNotNone(row1)
                self.assertIsNotNone(row2)
            finally:
                conn.close()

    def test_services_import_bundle_json_smoke(self):
        # Minimal bundle; importer should accept Bundle with no entries
        bundle = {"resourceType": "Bundle", "type": "collection", "entry": []}
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "mdr.sqlite")
            svc = MDRServices(db_path=db_path)
            res = svc.import_bundle_json(bundle, source_name="test:bundle", extract_references=False)
            self.assertTrue(res.ok, res.message)

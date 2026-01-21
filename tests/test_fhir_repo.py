import json
import tempfile
import unittest
from pathlib import Path

from mdr_gtk.db import connect
from mdr_gtk.util import read_text
from mdr_gtk.fhir_ingest import import_fhir_bundle_json
from mdr_gtk.fhir_repo import get_curated_by_ident, get_variants_for_curated, get_raw_json_by_sha


class TestFhirRepo(unittest.TestCase):
    def _init_db(self, db_path: str) -> None:
        conn = connect(db_path)
        try:
            conn.executescript(read_text("migrations/schema.sql"))
            conn.commit()
        finally:
            conn.close()

    def test_curated_lookup_and_variants(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "t.sqlite")
            self._init_db(db_path)

            bundle = {
                "resourceType": "Bundle",
                "type": "collection",
                "entry": [
                    {"resource": {"resourceType":"Patient","id":"p1","gender":"female"}},
                    {"resource": {"resourceType":"Observation","id":"o1","status":"final","code":{"text":"x"},"subject":{"reference":"Patient/p1"}}},
                ],
            }
            conn = connect(db_path)
            try:
                r = import_fhir_bundle_json(conn, bundle, source_name="repo-test", extract_references=False)
                self.assertTrue(r.ok, r.message)

                # curated for Patient should exist
                info = get_curated_by_ident(conn, "p1")
                self.assertIsNotNone(info)
                self.assertEqual(info.resource_type, "Patient")

                vars = get_variants_for_curated(conn, info.curated_id)
                self.assertTrue(len(vars) >= 1)

                raw = get_raw_json_by_sha(conn, info.current_sha256)
                self.assertIsInstance(raw, dict)
                self.assertEqual(raw.get("resourceType"), "Patient")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()

import unittest
import sqlite3
import json
from contextlib import closing

from mdr_gtk.fhir_selected_export import build_selected_bundle

class TestG3SelectedExport(unittest.TestCase):
    def test_empty_selection(self):
        with closing(sqlite3.connect(":memory:")) as conn:
            # create minimal tables expected by helper callers
            conn.executescript("""
                CREATE TABLE fhir_curated_resource(
                  ident TEXT PRIMARY KEY,
                  current_sha256 TEXT NOT NULL,
                  resource_type TEXT NOT NULL,
                  canonical_url TEXT,
                  logical_id TEXT,
                  artifact_version TEXT,
                  has_conflict INTEGER NOT NULL DEFAULT 0,
                  last_seen_ts TEXT
                );
                CREATE TABLE fhir_raw_resource(
                  sha256 TEXT PRIMARY KEY,
                  json TEXT
                );
                """
            )
            bundle, count = build_selected_bundle(conn, [])
        self.assertEqual(count, 0)
        self.assertEqual(bundle["resourceType"], "Bundle")
        self.assertEqual(bundle["type"], "collection")
        self.assertEqual(bundle["entry"], [])

if __name__ == "__main__":
    unittest.main()

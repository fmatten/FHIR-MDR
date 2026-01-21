import unittest
from mdr_gtk.fhir_filter import CuratedFilter, build_curated_query

class TestG3Filters(unittest.TestCase):
    def test_build_query_basic(self):
        f = CuratedFilter(resource_type=None, text=None, conflicts_only=False, limit=123)
        sql, params = build_curated_query(f)
        self.assertIn("FROM fhir_curated_resource", sql)
        self.assertTrue(sql.strip().endswith("LIMIT ?"))
        self.assertEqual(params[-1], 123)

    def test_build_query_all_filters(self):
        f = CuratedFilter(resource_type="StructureDefinition", text="patient", conflicts_only=True, limit=10)
        sql, params = build_curated_query(f)
        self.assertIn("resource_type = ?", sql)
        self.assertIn("has_conflict = 1", sql)
        self.assertEqual(params[-1], 10)

if __name__ == "__main__":
    unittest.main()

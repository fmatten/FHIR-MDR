import json
import tempfile
import unittest
from pathlib import Path

import sqlite3

from mdr_gtk.db import connect
from mdr_gtk.util import read_text
from mdr_gtk.fhir_ingest import import_fhir_bundle_json, import_fhir_package
from mdr_gtk.fhir_export import export_curated_bundle_json, export_curated_bundle_xml
from mdr_gtk.fhir_xml import resource_to_xml_element
from mdr_gtk.validator import run_external_validator


class TestFHIRSchemaAndImport(unittest.TestCase):
    def _init_db(self, db_path: str) -> None:
        conn = connect(db_path)
        try:
            conn.executescript(read_text("migrations/schema.sql"))
            conn.commit()
        finally:
            conn.close()

    def test_schema_applies(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "t.sqlite")
            self._init_db(db_path)
            conn = connect(db_path)
            try:
                row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fhir_ingest_run'").fetchone()
                self.assertIsNotNone(row)
            finally:
                conn.close()

    def test_import_bundle_json(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "t.sqlite")
            self._init_db(db_path)

            sample = Path(__file__).with_name("sample_bundle.json")
            bundle = json.loads(sample.read_text(encoding="utf-8"))

            conn = connect(db_path)
            try:
                res = import_fhir_bundle_json(conn, bundle, source_name="test")
                self.assertTrue(res.ok, res.message)
                raw = conn.execute("SELECT COUNT(*) FROM fhir_raw_resource").fetchone()[0]
                curated = conn.execute("SELECT COUNT(*) FROM fhir_curated_resource").fetchone()[0]
                self.assertEqual(raw, 2)
                self.assertEqual(curated, 2)
            finally:
                conn.close()

    def test_conflict_flag(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "t.sqlite")
            self._init_db(db_path)

            sample = Path(__file__).with_name("sample_bundle.json")
            bundle = json.loads(sample.read_text(encoding="utf-8"))

            conn = connect(db_path)
            try:
                import_fhir_bundle_json(conn, bundle, source_name="t1", extract_references=False)
                # mutate Patient to different sha, same identity (logical_id)
                bundle2 = json.loads(sample.read_text(encoding="utf-8"))
                bundle2["entry"][0]["resource"]["gender"] = "male"
                import_fhir_bundle_json(conn, bundle2, source_name="t2", extract_references=False)

                conflicts = conn.execute("SELECT COUNT(*) FROM fhir_curated_resource WHERE has_conflict=1").fetchone()[0]
                self.assertGreaterEqual(conflicts, 1)
            finally:
                conn.close()

def test_export_bundle_json_and_xml(self):
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.sqlite")
        self._init_db(db_path)

        sample = Path(__file__).with_name("sample_bundle.json")
        bundle = json.loads(sample.read_text(encoding="utf-8"))

        conn = connect(db_path)
        try:
            res = import_fhir_bundle_json(conn, bundle, source_name="t", extract_references=False)
            self.assertTrue(res.ok, res.message)

            out_json = str(Path(td) / "out.bundle.json")
            out_xml = str(Path(td) / "out.bundle.xml")

            ej = export_curated_bundle_json(conn, out_json, limit=100)
            self.assertTrue(ej.ok, ej.message)
            self.assertTrue(Path(out_json).exists())
            obj = json.loads(Path(out_json).read_text(encoding="utf-8"))
            self.assertEqual(obj.get("resourceType"), "Bundle")
            self.assertEqual(len(obj.get("entry", [])), 2)

            ex = export_curated_bundle_xml(conn, out_xml, limit=100)
            self.assertTrue(ex.ok, ex.message)
            self.assertTrue(Path(out_xml).exists())
            # well-formed xml
            import xml.etree.ElementTree as ET
            tree = ET.parse(out_xml)
            root = tree.getroot()
            self.assertTrue(root.tag.endswith("Bundle"))
        finally:
            conn.close()

def test_export_bundle_xml_strict_patient_observation(self):
    # Build a minimal Bundle with Patient + Observation only, then strict export should succeed.
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.sqlite")
        self._init_db(db_path)

        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": {"resourceType":"Patient","id":"pat-1","gender":"female","birthDate":"1990-01-01"}},
                {"resource": {"resourceType":"Observation","id":"obs-1","status":"final","code":{"text":"demo"}, "subject":{"reference":"Patient/pat-1"}}},
            ],
        }

        conn = connect(db_path)
        try:
            r = import_fhir_bundle_json(conn, bundle, source_name="strict-test", extract_references=False)
            self.assertTrue(r.ok, r.message)

            out_xml = str(Path(td) / "out.strict.bundle.xml")
            ex = export_curated_bundle_xml(conn, out_xml, limit=100, mode="strict")
            self.assertTrue(ex.ok, ex.message)

            xml_text = Path(out_xml).read_text(encoding="utf-8")
            # Quick ordering sanity: in Patient, id should appear before gender
            self.assertLess(xml_text.find("<Patient"), xml_text.find("<gender"))
            self.assertLess(xml_text.find("<id"), xml_text.find("<gender"))
        finally:
            conn.close()

def test_strict_rejects_unknown_fields(self):
    # Patient with an unknown field should be rejected in strict mode
    patient = {"resourceType":"Patient","id":"p1","gender":"female","unknownField":"x"}
    res = resource_to_xml_element(patient, mode="strict")
    self.assertFalse(res.ok)

def test_export_bundle_xml_strict_encounter_condition_conformance(self):
    # Strict export should succeed for a bundle that contains only supported types.
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.sqlite")
        self._init_db(db_path)

        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": {"resourceType":"Patient","id":"pat-1","gender":"female","birthDate":"1990-01-01"}},
                {"resource": {"resourceType":"Encounter","id":"enc-1","status":"finished","class":{"system":"http://terminology.hl7.org/CodeSystem/v3-ActCode","code":"AMB"},"subject":{"reference":"Patient/pat-1"}}},
                {"resource": {"resourceType":"Condition","id":"cond-1","code":{"text":"demo condition"},"subject":{"reference":"Patient/pat-1"}}},
                {"resource": {"resourceType":"Observation","id":"obs-1","status":"final","code":{"text":"demo obs"}, "subject":{"reference":"Patient/pat-1"}}},
                {"resource": {"resourceType":"StructureDefinition","id":"sd-1","url":"http://example.org/fhir/StructureDefinition/demo","version":"1.0.0","name":"DemoProfile","status":"draft","kind":"resource","abstract":False,"type":"Patient","derivation":"constraint","differential":{"element":[]}}},
                {"resource": {"resourceType":"ValueSet","id":"vs-1","url":"http://example.org/fhir/ValueSet/demo","version":"1.0.0","name":"DemoVS","status":"draft","compose":{"include":[]}}},
                {"resource": {"resourceType":"CodeSystem","id":"cs-1","url":"http://example.org/fhir/CodeSystem/demo","version":"1.0.0","name":"DemoCS","status":"draft","content":"complete","concept":[]}},
            ],
        }

        conn = connect(db_path)
        try:
            r = import_fhir_bundle_json(conn, bundle, source_name="strict-d21", extract_references=False)
            self.assertTrue(r.ok, r.message)

            out_xml = str(Path(td) / "out.strict.d21.bundle.xml")
            ex = export_curated_bundle_xml(conn, out_xml, limit=200, mode="strict")
            self.assertTrue(ex.ok, ex.message)

            xml_text = Path(out_xml).read_text(encoding="utf-8")
            # sanity: ensure key tags exist
            self.assertIn("<Bundle", xml_text)
            self.assertIn("<Patient", xml_text)
            self.assertIn("<Encounter", xml_text)
            self.assertIn("<Condition", xml_text)
            self.assertIn("<StructureDefinition", xml_text)
            self.assertIn("<ValueSet", xml_text)
            self.assertIn("<CodeSystem", xml_text)
        finally:
            conn.close()

def test_strict_rejects_unknown_fields_encounter(self):
    enc = {"resourceType":"Encounter","id":"e1","status":"finished","unknownField":"x"}
    res = resource_to_xml_element(enc, mode="strict")
    self.assertFalse(res.ok)

def test_export_bundle_xml_strict_medicationrequest_procedure(self):
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.sqlite")
        self._init_db(db_path)

        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": {"resourceType":"Patient","id":"pat-1","gender":"female","birthDate":"1990-01-01"}},
                {"resource": {"resourceType":"MedicationRequest","id":"mr-1","status":"active","intent":"order",
                              "medicationCodeableConcept":{"text":"Amoxicillin"},
                              "subject":{"reference":"Patient/pat-1"}}},
                {"resource": {"resourceType":"Procedure","id":"pr-1","status":"completed",
                              "code":{"text":"Appendectomy"},
                              "subject":{"reference":"Patient/pat-1"}}},
            ],
        }

        conn = connect(db_path)
        try:
            r = import_fhir_bundle_json(conn, bundle, source_name="strict-d22", extract_references=False)
            self.assertTrue(r.ok, r.message)

            out_xml = str(Path(td) / "out.strict.d22.bundle.xml")
            ex = export_curated_bundle_xml(conn, out_xml, limit=200, mode="strict")
            self.assertTrue(ex.ok, ex.message)

            xml_text = Path(out_xml).read_text(encoding="utf-8")
            self.assertIn("<MedicationRequest", xml_text)
            self.assertIn("<Procedure", xml_text)
        finally:
            conn.close()

def test_strictish_fallback_unknown_and_unsupported(self):
    # Unknown field in supported type should fallback in strictish
    enc = {"resourceType":"Encounter","id":"e1","status":"finished","unknownField":"x"}
    res = resource_to_xml_element(enc, mode="strictish")
    self.assertTrue(res.ok)
    self.assertIsNotNone(res.element)

    # Unsupported type should fallback in strictish
    org = {"resourceType":"Organization","id":"o1","name":"ACME"}
    res2 = resource_to_xml_element(org, mode="strictish")
    self.assertTrue(res2.ok)
    self.assertIsNotNone(res2.element)

def test_export_bundle_xml_strict_medication_medicationdispense(self):
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.sqlite")
        self._init_db(db_path)

        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": {"resourceType":"Patient","id":"pat-1","gender":"female","birthDate":"1990-01-01"}},
                {"resource": {"resourceType":"Medication","id":"med-1","code":{"text":"Amoxicillin 500mg"}}},
                {"resource": {"resourceType":"MedicationDispense","id":"md-1","status":"completed",
                              "medicationReference":{"reference":"Medication/med-1"},
                              "subject":{"reference":"Patient/pat-1"},
                              "whenHandedOver":"2026-01-20T12:00:00Z",
                              "quantity":{"value":20,"unit":"tablet"}}},
            ],
        }

        conn = connect(db_path)
        try:
            r = import_fhir_bundle_json(conn, bundle, source_name="strict-d23", extract_references=False)
            self.assertTrue(r.ok, r.message)

            out_xml = str(Path(td) / "out.strict.d23.bundle.xml")
            ex = export_curated_bundle_xml(conn, out_xml, limit=200, mode="strict")
            self.assertTrue(ex.ok, ex.message)

            xml_text = Path(out_xml).read_text(encoding="utf-8")
            self.assertIn("<Medication", xml_text)
            self.assertIn("<MedicationDispense", xml_text)
            # Ensure primitive value attribute exists for status
            self.assertIn("<status value=\"completed\"/>", xml_text)
        finally:
            conn.close()

def test_strictish_mixed_bundle_does_not_abort(self):
    # strictish should export even with unsupported types by falling back.
    mixed = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"resource": {"resourceType":"Patient","id":"p1","gender":"female"}},
            {"resource": {"resourceType":"Organization","id":"o1","name":"ACME Hospital"}},
            {"resource": {"resourceType":"MedicationRequest","id":"mr1","status":"active","intent":"order","medicationCodeableConcept":{"text":"Ibuprofen"},"subject":{"reference":"Patient/p1"}}},
        ],
    }
    res = resource_to_xml_element(mixed, mode="strictish")
    self.assertTrue(res.ok)
    self.assertIsNotNone(res.element)

def test_medicationdispense_authorizingprescription_xml(self):
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.sqlite")
        self._init_db(db_path)

        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": {"resourceType":"Patient","id":"pat-1","gender":"female"}},
                {"resource": {"resourceType":"MedicationRequest","id":"mr-1","status":"active","intent":"order",
                              "medicationCodeableConcept":{"text":"Ibuprofen"},
                              "subject":{"reference":"Patient/pat-1"}}},
                {"resource": {"resourceType":"MedicationDispense","id":"md-1","status":"completed",
                              "medicationCodeableConcept":{"text":"Ibuprofen"},
                              "subject":{"reference":"Patient/pat-1"},
                              "authorizingPrescription":[{"reference":"MedicationRequest/mr-1"}]}}
            ],
        }

        conn = connect(db_path)
        try:
            r = import_fhir_bundle_json(conn, bundle, source_name="d24", extract_references=False)
            self.assertTrue(r.ok, r.message)

            out_xml = str(Path(td) / "out.d24.strict.bundle.xml")
            ex = export_curated_bundle_xml(conn, out_xml, limit=200, mode="strict")
            self.assertTrue(ex.ok, ex.message)

            xml_text = Path(out_xml).read_text(encoding="utf-8")
            self.assertIn("<authorizingPrescription>", xml_text)
            self.assertIn('value="MedicationRequest/mr-1"', xml_text)
        finally:
            conn.close()

def test_optional_external_validator_hook(self):
    # This test is optional and only runs if you configure:
    #   export FHIR_VALIDATOR_TEMPLATE='java -jar /path/validator_cli.jar {file} -version 4.0.1'
    with tempfile.TemporaryDirectory() as td:
        out_xml = str(Path(td) / "dummy.bundle.xml")
        Path(out_xml).write_text('<?xml version="1.0" encoding="utf-8"?><Bundle xmlns="http://hl7.org/fhir"><type value="collection"/></Bundle>', encoding="utf-8")

        res = run_external_validator(out_xml, mode="xml")
        if res is None:
            self.skipTest("FHIR_VALIDATOR_TEMPLATE not configured")
        # If configured, we at least assert the command ran. Success depends on user's validator setup.
        self.assertIsNotNone(res)
        self.assertIsInstance(res.returncode, int)


if __name__ == "__main__":
    unittest.main()


def test_import_package_tgz(self):
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.sqlite")
        self._init_db(db_path)

        pkg = Path(__file__).with_name("sample_package.tgz")
        conn = connect(db_path)
        try:
            res = import_fhir_package(conn, str(pkg), source_name="pkgtest")
            self.assertTrue(res.ok, res.message)
            raw = conn.execute("SELECT COUNT(*) FROM fhir_raw_resource").fetchone()[0]
            curated = conn.execute("SELECT COUNT(*) FROM fhir_curated_resource").fetchone()[0]
            # patient + SD + obs from bundle.json
            self.assertEqual(raw, 3)
            self.assertEqual(curated, 3)
        finally:
            conn.close()

def test_dedup_across_runs(self):
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.sqlite")
        self._init_db(db_path)

        pkg_dir = Path(__file__).with_name("sample_package_dir") / "package"
        conn = connect(db_path)
        try:
            r1 = import_fhir_package(conn, str(pkg_dir), source_name="pkg1")
            self.assertTrue(r1.ok, r1.message)
            r2 = import_fhir_package(conn, str(pkg_dir), source_name="pkg2")
            self.assertTrue(r2.ok, r2.message)

            curated = conn.execute("SELECT COUNT(*) FROM fhir_curated_resource").fetchone()[0]
            self.assertEqual(curated, 3)  # identities stable

            # variants occurrences should be >=2 for at least one curated
            occ = conn.execute("SELECT MAX(occurrences) FROM fhir_curated_variant").fetchone()[0]
            self.assertGreaterEqual(occ, 2)
        finally:
            conn.close()

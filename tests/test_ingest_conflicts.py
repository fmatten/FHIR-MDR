
## 2) `tests/test_ingest_conflicts.py`
```python
import os
import json
import sqlite3
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

def run_cli(module: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # Ensure repo-root imports work even without installation
    env["PYTHONPATH"] = str(cwd)
    cmd = [os.environ.get("PYTHON", "python3"), "-m", module, *args]
    return subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True)

def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None

def pick_table(conn: sqlite3.Connection, candidates: list[str]) -> str | None:
    for t in candidates:
        if table_exists(conn, t):
            return t
    return None

class TestIngestDedupeAndConflicts(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.db_path = self.tmpdir / "mdr.sqlite"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make_bundle_json(self, canonical: str, version: str, name: str) -> Path:
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {
                    "resource": {
                        "resourceType": "StructureDefinition",
                        "id": "sd-1",
                        "url": canonical,
                        "version": version,
                        "name": name,
                        "status": "active",
                        "kind": "resource",
                        "abstract": False,
                        "type": "Patient",
                        "derivation": "constraint",
                        "differential": {"element": [{"id": "Patient"}]},
                    }
                }
            ],
        }
        p = self.tmpdir / f"bundle_{version}.json"
        p.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        return p

    def _make_bundle_xml_minimal(self) -> Path:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<Bundle xmlns="http://hl7.org/fhir">
  <type value="collection"/>
  <entry>
    <resource>
      <ValueSet>
        <id value="vs-1"/>
        <url value="http://example.org/fhir/ValueSet/vs-1"/>
        <status value="active"/>
      </ValueSet>
    </resource>
  </entry>
</Bundle>
"""
        p = self.tmpdir / "bundle.xml"
        p.write_text(xml, encoding="utf-8")
        return p

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_import_bundle_json_creates_curated(self) -> None:
        bundle = self._make_bundle_json(
            "http://example.org/fhir/StructureDefinition/demo",
            "1.0.0",
            "DemoSD",
        )
        cp = run_cli(
            "mdr_gtk.scripts.import_fhir_bundle",
            ["--db", str(self.db_path), str(bundle)],
            REPO_ROOT,
        )
        self.assertEqual(cp.returncode, 0, msg=f"STDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")

        with self._open() as conn:
            curated = pick_table(conn, ["fhir_curated", "fhir_curated_artifact", "fhir_curated_resource"])
            self.assertIsNotNone(curated, "Could not find curated table (expected something like fhir_curated).")
            n = conn.execute(f"SELECT COUNT(*) AS c FROM {curated}").fetchone()["c"]
            self.assertGreaterEqual(n, 1)

    def test_import_bundle_xml_creates_curated(self) -> None:
        xml = self._make_bundle_xml_minimal()
        cp = run_cli(
            "mdr_gtk.scripts.import_fhir_bundle",
            ["--db", str(self.db_path), str(xml)],
            REPO_ROOT,
        )
        self.assertEqual(cp.returncode, 0, msg=f"STDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")

        with self._open() as conn:
            curated = pick_table(conn, ["fhir_curated", "fhir_curated_artifact", "fhir_curated_resource"])
            self.assertIsNotNone(curated)
            n = conn.execute(f"SELECT COUNT(*) AS c FROM {curated}").fetchone()["c"]
            self.assertGreaterEqual(n, 1)

    def test_conflict_same_canonical_different_bytes(self) -> None:
        canonical = "http://example.org/fhir/StructureDefinition/conflict"
        b1 = self._make_bundle_json(canonical, "1.0.0", "ConflictA")
        b2 = self._make_bundle_json(canonical, "1.0.1", "ConflictB")

        cp1 = run_cli("mdr_gtk.scripts.import_fhir_bundle", ["--db", str(self.db_path), str(b1)], REPO_ROOT)
        self.assertEqual(cp1.returncode, 0, msg=f"STDOUT:\n{cp1.stdout}\nSTDERR:\n{cp1.stderr}")

        time.sleep(1)

        cp2 = run_cli("mdr_gtk.scripts.import_fhir_bundle", ["--db", str(self.db_path), str(b2)], REPO_ROOT)
        self.assertEqual(cp2.returncode, 0, msg=f"STDOUT:\n{cp2.stdout}\nSTDERR:\n{cp2.stderr}")

        with self._open() as conn:
            curated = pick_table(conn, ["fhir_curated", "fhir_curated_artifact", "fhir_curated_resource"])
            self.assertIsNotNone(curated)

            cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({curated})").fetchall()]
            if "canonical_url" not in cols or "has_conflict" not in cols:
                self.skipTest(f"Curated table {curated} does not expose canonical_url/has_conflict columns (cols={cols})")

            row = conn.execute(
                f"SELECT canonical_url, has_conflict FROM {curated} WHERE canonical_url=?",
                (canonical,),
            ).fetchone()
            self.assertIsNotNone(row, "Expected curated row for the canonical URL")
            self.assertEqual(int(row["has_conflict"]), 1)

            variants = pick_table(conn, ["fhir_variant", "fhir_variants", "fhir_curated_variant"])
            if variants:
                vcols = [r["name"] for r in conn.execute(f"PRAGMA table_info({variants})").fetchall()]
                if "canonical_url" in vcols:
                    vc = conn.execute(
                        f"SELECT COUNT(*) AS c FROM {variants} WHERE canonical_url=?",
                        (canonical,),
                    ).fetchone()["c"]
                    self.assertGreaterEqual(vc, 2)

    def test_last_seen_ts_desc_sort(self) -> None:
        b1 = self._make_bundle_json("http://example.org/fhir/StructureDefinition/sort1", "1.0.0", "Sort1")
        b2 = self._make_bundle_json("http://example.org/fhir/StructureDefinition/sort2", "1.0.0", "Sort2")

        cp1 = run_cli("mdr_gtk.scripts.import_fhir_bundle", ["--db", str(self.db_path), str(b1)], REPO_ROOT)
        self.assertEqual(cp1.returncode, 0, msg=f"STDOUT:\n{cp1.stdout}\nSTDERR:\n{cp1.stderr}")
        time.sleep(1)
        cp2 = run_cli("mdr_gtk.scripts.import_fhir_bundle", ["--db", str(self.db_path), str(b2)], REPO_ROOT)
        self.assertEqual(cp2.returncode, 0, msg=f"STDOUT:\n{cp2.stdout}\nSTDERR:\n{cp2.stderr}")

        with self._open() as conn:
            curated = pick_table(conn, ["fhir_curated", "fhir_curated_artifact", "fhir_curated_resource"])
            self.assertIsNotNone(curated)
            cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({curated})").fetchall()]
            if "last_seen_ts" not in cols or "canonical_url" not in cols:
                self.skipTest(f"Curated table {curated} does not expose last_seen_ts/canonical_url columns (cols={cols})")

            rows = conn.execute(
                f"SELECT canonical_url, last_seen_ts FROM {curated} ORDER BY last_seen_ts DESC LIMIT 2"
            ).fetchall()
            self.assertGreaterEqual(len(rows), 2)
            self.assertEqual(rows[0]["canonical_url"], "http://example.org/fhir/StructureDefinition/sort2")

import os
import json
import tarfile
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

def run_cli(module: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(cwd)
    cmd = [os.environ.get("PYTHON", "python3"), "-m", module, *args]
    return subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True)

def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None

def pick_table(conn: sqlite3.Connection, candidates: list[str]) -> str | None:
    for t in candidates:
        if table_exists(conn, t):
            return t
    return None

class TestPackageImport(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.db_path = self.tmpdir / "mdr.sqlite"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make_minimal_package_tgz(self) -> Path:
        pkg_root = self.tmpdir / "pkg"
        pkg_dir = pkg_root / "package"
        pkg_dir.mkdir(parents=True)

        (pkg_dir / "package.json").write_text(json.dumps({
            "name": "example.fhir.mdr.test",
            "version": "0.0.0",
            "fhirVersions": ["4.0.1"],
            "description": "Minimal test package for FHIR-MDR"
        }, indent=2), encoding="utf-8")

        sd = {
            "resourceType": "StructureDefinition",
            "id": "sd-test",
            "url": "http://example.org/fhir/StructureDefinition/pkg-test",
            "version": "0.0.0",
            "name": "PkgTest",
            "status": "active",
            "kind": "resource",
            "abstract": False,
            "type": "Patient",
            "derivation": "constraint",
            "differential": {"element": [{"id": "Patient"}]},
        }
        (pkg_dir / "StructureDefinition-sd-test.json").write_text(json.dumps(sd, indent=2), encoding="utf-8")

        tgz_path = self.tmpdir / "sample_package.tgz"
        with tarfile.open(tgz_path, "w:gz") as tf:
            for p in pkg_dir.rglob("*"):
                arcname = str(Path("package") / p.relative_to(pkg_dir))
                tf.add(p, arcname=arcname)
        return tgz_path

    def test_import_package_tgz_creates_curated(self) -> None:
        tgz = self._make_minimal_package_tgz()
        cp = run_cli("mdr_gtk.scripts.import_fhir_package", ["--db", str(self.db_path), str(tgz)], REPO_ROOT)
        self.assertEqual(cp.returncode, 0, msg=f"STDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            curated = pick_table(conn, ["fhir_curated", "fhir_curated_artifact", "fhir_curated_resource"])
            self.assertIsNotNone(curated, "Could not find curated table after import.")
            n = conn.execute(f"SELECT COUNT(*) AS c FROM {curated}").fetchone()["c"]
            self.assertGreaterEqual(n, 1)
        finally:
            conn.close()

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REQUIRED_ACTIONS = [
    "export_json",
    "import_json",
    "export_csv",
    "export_skos",
    "open_db",
    "new_db",
    "import_fhir_bundle",
    "import_fhir_package",
    "export_fhir_bundle_json",
    "export_fhir_bundle_xml",
]


@dataclass
class DiagnosticResult:
    ok: bool
    lines: list[str]


def run_diagnostics(project_root: str | None = None) -> DiagnosticResult:
    """Lightweight startup diagnostics.

    - Checks that key files exist (migrations/schema.sql)
    - Checks that critical imports work
    - Returns a short report suitable for console/log panel.

    This does NOT require a display and is safe in headless runs.
    """
    lines: list[str] = []
    ok = True

    try:
        import mdr_gtk  # noqa
        lines.append("OK: mdr_gtk import")
    except Exception as e:
        ok = False
        lines.append(f"FAIL: import mdr_gtk: {e}")

    # Check schema file
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[1]
    schema = root / "migrations" / "schema.sql"
    if schema.exists():
        lines.append(f"OK: schema file present ({schema})")
    else:
        ok = False
        lines.append(f"FAIL: missing schema.sql at {schema}")

    # Optional: gi availability
    try:
        import gi  # noqa
        lines.append("OK: PyGObject (gi) import")
    except Exception as e:
        # Not fatal for CLI/tests, but fatal for GUI runs
        lines.append(f"WARN: PyGObject (gi) not available: {e}")

    return DiagnosticResult(ok=ok, lines=lines)

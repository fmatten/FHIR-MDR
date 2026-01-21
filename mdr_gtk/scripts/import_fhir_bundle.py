"""Import a FHIR R4 Bundle (JSON) into the MDR SQLite DB (FHIR ingest layer)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mdr_gtk.db import connect
from mdr_gtk.fhir_ingest import import_fhir_bundle_json
from mdr_gtk.util import read_text


from mdr_gtk.util import read_text

def ensure_schema_applied(conn) -> None:
    """Auto-apply schema if FHIR tables are missing (makes CLI usage foolproof)."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fhir_ingest_run'"
    ).fetchone()
    if row is None:
        conn.executescript(read_text("migrations/schema.sql"))
        conn.commit()

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="SQLite DB path")
    p.add_argument("--source", default=None, help="Source name for ingest run")
    p.add_argument("--partition", default=None, help="Optional partition key")
    p.add_argument("--no-refs", action="store_true", help="Do not extract reference edges")
    p.add_argument("bundle_json", help="Path to FHIR Bundle JSON")
    args = p.parse_args()

    bundle_path = Path(args.bundle_json)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    conn = connect(args.db)
    ensure_schema_applied(conn)
    try:
        res = import_fhir_bundle_json(
            conn,
            bundle,
            source_name=args.source or f"file:{bundle_path.name}",
            partition_key=args.partition,
            extract_references=not args.no_refs,
        )
    finally:
        conn.close()

    if not res.ok:
        raise SystemExit(res.message)
    print(res.message)


if __name__ == "__main__":
    main()

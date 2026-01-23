"""Import a FHIR R4 Bundle (JSON or XML) into the MDR SQLite DB (FHIR ingest layer)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mdr_gtk.db import connect
from mdr_gtk.fhir_ingest import import_fhir_bundle_json
from mdr_gtk.util import read_text


from mdr_gtk.services import ensure_schema_applied


def _detect_xml(bundle_path: Path, text: str) -> bool:
    """Best-effort detection: file extension or leading '<'."""
    if bundle_path.suffix.lower() in (".xml",):
        return True
    return text.lstrip().startswith("<")


def _import_bundle_xml(conn, xml_text: str, *, source_name: str, partition_key: str | None, extract_references: bool):
    """Call the XML importer if available."""
    import mdr_gtk.fhir_ingest as ingest  # local import to avoid hard dependency at import-time

    fn = getattr(ingest, "import_fhir_bundle_xml", None)
    if fn is None:
        raise SystemExit(
            "XML import is not available in this build: "
            "missing mdr_gtk.fhir_ingest.import_fhir_bundle_xml. "
            "Please update fhir_ingest.py to expose an XML bundle importer."
        )

    return fn(
        conn,
        xml_text,
        source_name=source_name,
        partition_key=partition_key,
        extract_references=extract_references,
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Import a FHIR Bundle (JSON or XML) into the MDR SQLite DB.")
    p.add_argument("--db", required=True, help="SQLite DB path")
    p.add_argument("--source", default=None, help="Source name for ingest run")
    p.add_argument("--partition", default=None, help="Optional partition key")
    p.add_argument("--no-refs", action="store_true", help="Do not extract reference edges")
    p.add_argument("bundle", help="Path to FHIR Bundle (JSON or XML)")
    args = p.parse_args()

    bundle_path = Path(args.bundle)
    if not bundle_path.exists():
        raise SystemExit(f"Bundle file not found: {bundle_path}")

    raw_text = bundle_path.read_text(encoding="utf-8", errors="replace")
    is_xml = _detect_xml(bundle_path, raw_text)

    conn = connect(args.db)
    ensure_schema_applied(conn)
    try:
        source_name = args.source or f"file:{bundle_path.name}"
        extract_refs = not args.no_refs

        if is_xml:
            res = _import_bundle_xml(
                conn,
                raw_text,
                source_name=source_name,
                partition_key=args.partition,
                extract_references=extract_refs,
            )
        else:
            bundle_obj = json.loads(raw_text)
            res = import_fhir_bundle_json(
                conn,
                bundle_obj,
                source_name=source_name,
                partition_key=args.partition,
                extract_references=extract_refs,
            )
    finally:
        conn.close()

    if not res.ok:
        raise SystemExit(res.message)
    print(res.message)


if __name__ == "__main__":
    main()

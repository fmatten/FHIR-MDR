"""Export curated FHIR resources as a Bundle (xml)."""

from __future__ import annotations

import argparse
from pathlib import Path

from mdr_gtk.db import connect
from mdr_gtk.util import read_text
from mdr_gtk.fhir_export import export_curated_bundle_xml


def ensure_schema_applied(conn) -> None:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fhir_ingest_run'"
    ).fetchone()
    if row is None:
        conn.executescript(read_text("migrations/schema.sql"))
        conn.commit()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="SQLite DB path")
    p.add_argument("--out", default=None, help="Output file path")
    p.add_argument("--limit", type=int, default=500, help="Max curated resources")
    p.add_argument("--mode", default="best-effort", choices=["best-effort","strict","strictish"], help="XML serialization mode")
    args = p.parse_args()

    out = args.out
    if out is None:
        out = str(Path(args.db).with_suffix(".export.bundle.xml"))
    conn = connect(args.db)
    ensure_schema_applied(conn)
    try:
        res = export_curated_bundle_xml(conn, out, limit=args.limit, mode=args.mode)
    finally:
        conn.close()

    if not res.ok:
        raise SystemExit(res.message)
    print(res.message)


if __name__ == "__main__":
    main()

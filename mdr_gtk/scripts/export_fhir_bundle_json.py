"""Export curated FHIR resources as a Bundle (json)."""

from __future__ import annotations

import argparse
from pathlib import Path

from mdr_gtk.db import connect
from mdr_gtk.util import read_text
from mdr_gtk.fhir_export import export_curated_bundle_json


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
    args = p.parse_args()

    out = args.out
    if out is None:
        out = str(Path(args.db).with_suffix(".export.bundle.json"))
    conn = connect(args.db)
    ensure_schema_applied(conn)
    try:
        res = export_curated_bundle_json(conn, out, limit=args.limit)
    finally:
        conn.close()

    if not res.ok:
        raise SystemExit(res.message)
    print(res.message)


if __name__ == "__main__":
    main()

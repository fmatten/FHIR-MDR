"""Import a FHIR NPM package (.tgz/.tar.gz) or an unpacked directory."""

from __future__ import annotations

import argparse
from pathlib import Path

from mdr_gtk.db import connect
from mdr_gtk.fhir_ingest import import_fhir_package


from mdr_gtk.services import ensure_schema_applied


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="SQLite DB path")
    p.add_argument("--source", default=None, help="Source name for ingest run")
    p.add_argument("--partition", default=None, help="Optional partition key")
    p.add_argument("--refs", action="store_true", help="Extract reference edges (default: off)")
    p.add_argument("package_path", help="Path to .tgz/.tar.gz or unpacked directory")
    args = p.parse_args()

    pp = Path(args.package_path)

    conn = connect(args.db)
    ensure_schema_applied(conn)
    try:
        res = import_fhir_package(
            conn,
            str(pp),
            source_name=args.source or f"file:{pp.name}",
            partition_key=args.partition,
            extract_references=bool(args.refs),
        )
    finally:
        conn.close()

    if not res.ok:
        raise SystemExit(res.message)
    print(res.message)


if __name__ == "__main__":
    main()

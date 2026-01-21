"""
Export MDR content to a single JSON file.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from mdr_gtk.db import connect


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="mdr.sqlite")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    conn = connect(args.db)
    try:
        data: dict[str, object] = {}
        # Core tables
        for table in [
            "context",
            "registration_authority",
            "registrable_item",
            "conceptual_domain",
            "representation_class",
            "object_class",
            "property",
            "data_element_concept",
            "value_domain",
            "data_element",
            "designation",
            "permissible_value",
            "classification_scheme",
            "classification_item",
            "item_classification",
            "item_version",
        ]:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            data[table] = rows_to_dicts(rows)

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OK: Exported {out.resolve()}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

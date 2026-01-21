"""
Import MDR content from JSON (upsert by UUID).

Notes:
- registrable_item must be imported before 1:1 extension tables.
- order matters due to FKs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from mdr_gtk.db import connect


def upsert(conn, table: str, row: dict):
    cols = list(row.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    # SQLite upsert requires a conflict target; all our tables use uuid PK.
    update_cols = [c for c in cols if c != "uuid"]
    update_stmt = ", ".join([f"{c}=excluded.{c}" for c in update_cols]) if update_cols else ""
    if update_stmt:
        sql = f"INSERT INTO {table}({col_list}) VALUES({placeholders}) ON CONFLICT(uuid) DO UPDATE SET {update_stmt}"
    else:
        sql = f"INSERT INTO {table}({col_list}) VALUES({placeholders}) ON CONFLICT(uuid) DO NOTHING"
    conn.execute(sql, [row[c] for c in cols])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="mdr.sqlite")
    p.add_argument("--in", dest="infile", required=True)
    args = p.parse_args()

    path = Path(args.infile)
    data = json.loads(path.read_text(encoding="utf-8"))

    conn = connect(args.db)
    try:
        conn.execute("BEGIN;")

        # Order: no-FK -> base -> extensions -> relations
        for table in ["context", "registration_authority"]:
            for row in data.get(table, []):
                upsert(conn, table, row)

        for row in data.get("registrable_item", []):
            upsert(conn, "registrable_item", row)

        # 1:1 extension tables
        for table in [
            "conceptual_domain",
            "representation_class",
            "object_class",
            "property",
            "classification_scheme",
            "classification_item",
            "data_element_concept",
            "value_domain",
            "data_element",
        ]:
            for row in data.get(table, []):
                upsert(conn, table, row)

        # 1:n
        for table in ["designation", "permissible_value", "item_classification", "item_version"]:
            for row in data.get(table, []):
                upsert(conn, table, row)

        conn.commit()
        print(f"OK: Imported {path.resolve()} into {args.db}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()

"""
DB initialisieren (Schema anwenden, optional Seed-Daten).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3

from mdr_gtk.db import connect
from mdr_gtk.util import read_text


def apply_sql(conn: sqlite3.Connection, sql_text: str) -> None:
    conn.executescript(sql_text)
    conn.commit()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="mdr.sqlite", help="Pfad zur SQLite DB")
    p.add_argument("--seed", action="store_true", help="Seed-Daten einspielen")
    args = p.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(str(db_path))
    try:
        apply_sql(conn, read_text("migrations/schema.sql"))
        if args.seed:
            apply_sql(conn, read_text("migrations/seed.sql"))
    finally:
        conn.close()

    print(f"OK: DB initialisiert: {db_path.resolve()}")
    if args.seed:
        print("OK: Seed-Daten eingespielt")


if __name__ == "__main__":
    main()

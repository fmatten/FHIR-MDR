"""
Entry point: python3 -m mdr_gtk --db ./mdr.sqlite
"""
from __future__ import annotations

import argparse
from mdr_gtk.app import run_app


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="mdr.sqlite", help="Pfad zur SQLite DB")
    args = p.parse_args()
    run_app(args.db)


if __name__ == "__main__":
    main()

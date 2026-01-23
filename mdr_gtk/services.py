from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Any

from .db import connect
from .util import read_text
from .fhir_ingest import import_fhir_bundle_json, import_fhir_package

# NOTE:
# - sqlite3.Connection's context manager does NOT close the connection.
# - This module provides explicit connection lifecycle helpers for GUI + CLI,
#   and centralizes schema auto-application in one place.


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def ensure_schema_applied(conn) -> None:
    """Auto-apply the bundled schema if required tables are missing.

    This is used by CLI scripts and (optionally) by the GUI to make first-run
    usage foolproof: you can point to an empty SQLite file and the schema will
    be installed.
    """
    # We consider the DB initialized if both the ISO11179 core table and the
    # FHIR ingest table exist. (Either one missing indicates an uninitialized DB.)
    core_ok = _table_exists(conn, "registrable_item")
    fhir_ok = _table_exists(conn, "fhir_ingest_run")
    if not (core_ok and fhir_ok):
        conn.executescript(read_text("migrations/schema.sql"))
        conn.commit()


@contextmanager
def db_conn(db_path: str) -> Iterator[Any]:
    """Context manager that opens *and closes* an sqlite connection."""
    conn = connect(db_path)
    try:
        ensure_schema_applied(conn)
        yield conn
    finally:
        conn.close()


@dataclass(frozen=True)
class MDRServices:
    """Thin service façade used by the GUI.

    The goal is to keep GTK handlers free of SQL/DB lifecycle logic by routing
    operations through this service layer. The underlying modules (repositories,
    fhir_ingest, fhir_repo, etc.) remain reusable and tested.
    """

    db_path: str

    def connect(self):
        """Open a connection (callers must close). Prefer :meth:`conn` in new code."""
        conn = connect(self.db_path)
        ensure_schema_applied(conn)
        return conn

    @contextmanager
    def conn(self):
        """Open a connection and ensure it is closed."""
        with db_conn(self.db_path) as c:
            yield c

    # --- Ingest operations ---

    def import_bundle_json(self, bundle_obj: dict, *, source_name: str, partition_key: Optional[str] = None, extract_references: bool = True):
        with self.conn() as conn:
            return import_fhir_bundle_json(
                conn,
                bundle_obj,
                source_name=source_name,
                partition_key=partition_key,
                extract_references=extract_references,
            )

    def import_package(self, package_path: str, *, source_name: str, partition_key: Optional[str] = None, extract_references: bool = False):
        with self.conn() as conn:
            return import_fhir_package(
                conn,
                package_path,
                source_name=source_name,
                partition_key=partition_key,
                extract_references=extract_references,
            )

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from mdr_gtk.services import ensure_schema_applied
from mdr_gtk.fhir_ingest import import_fhir_bundle_json, import_fhir_package
from mdr_gtk.fhir_selected_export import export_selected_bundle_json, export_selected_bundle_xml


@dataclass
class GUIServiceFacade:
    """Thin service facade for GUI actions.

    Goal: keep Gtk callbacks free of DB/ingest/export details so we can test behavior
    without running GTK. This facade uses an *existing* SQLite connection owned by
    the UI, but it centralizes:
      - schema ensure
      - file parsing
      - consistent source naming

    (Later we can swap to per-action connections if needed.)
    """

    conn: sqlite3.Connection

    def ensure_schema(self) -> None:
        ensure_schema_applied(self.conn)

    # -------- FHIR imports --------
    def import_fhir_bundle_json_file(self, path: str, *, source_name: str | None = None):
        self.ensure_schema()
        p = Path(path)
        obj = json.loads(p.read_text(encoding="utf-8"))
        return import_fhir_bundle_json(self.conn, obj, source_name=source_name or f"file:{p.name}")

    def import_fhir_package_file(self, path: str, *, source_name: str | None = None, partition_key: str | None = None):
        self.ensure_schema()
        p = Path(path)
        return import_fhir_package(
            self.conn,
            str(p),
            source_name=source_name or f"file:{p.name}",
            partition_key=partition_key,
        )

    # -------- FHIR exports --------
    def export_selected_json(self, curated_idents: Sequence[str], out_path: str):
        self.ensure_schema()
        return export_selected_bundle_json(self.conn, curated_idents, out_path)

    def export_selected_xml(self, curated_idents: Sequence[str], out_path: str):
        self.ensure_schema()
        return export_selected_bundle_xml(self.conn, curated_idents, out_path)

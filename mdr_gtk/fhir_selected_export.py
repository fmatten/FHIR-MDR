from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from mdr_gtk.fhir_repo import get_curated_by_ident, get_raw_json_by_sha
from mdr_gtk.fhir_xml import resource_to_xml_element


@dataclass
class ExportResult:
    ok: bool
    message: str
    count: int = 0


def build_selected_bundle(conn: sqlite3.Connection, idents: Iterable[str]) -> tuple[dict[str, Any], int]:
    entries: list[dict[str, Any]] = []
    count = 0
    for ident in idents:
        info = get_curated_by_ident(conn, ident)
        if not info:
            continue
        raw = get_raw_json_by_sha(conn, info.current_sha256)
        if raw is None:
            continue
        entries.append({"resource": raw})
        count += 1
    bundle = {"resourceType": "Bundle", "type": "collection", "entry": entries}
    return bundle, count


def export_selected_bundle_json(conn: sqlite3.Connection, idents: Iterable[str], out_path: str) -> ExportResult:
    bundle, count = build_selected_bundle(conn, idents)
    Path(out_path).write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return ExportResult(ok=True, message=f"Exported {count} resources to {out_path}", count=count)


def export_selected_bundle_xml(conn: sqlite3.Connection, idents: Iterable[str], out_path: str, mode: str = "best-effort") -> ExportResult:
    bundle, count = build_selected_bundle(conn, idents)
    built = resource_to_xml_element(bundle, mode=mode)
    if not built.ok or built.element is None:
        return ExportResult(ok=False, message=built.message, count=0)
    import xml.etree.ElementTree as ET
    ET.ElementTree(built.element).write(out_path, encoding="utf-8", xml_declaration=True)
    return ExportResult(ok=True, message=f"Exported {count} resources to {out_path} (mode={mode})", count=count)

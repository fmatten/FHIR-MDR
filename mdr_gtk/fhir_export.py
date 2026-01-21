from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import xml.etree.ElementTree as ET

import sqlite3


FHIR_NS = "http://hl7.org/fhir"
ET.register_namespace("", FHIR_NS)


@dataclass
class ExportResult:
    ok: bool
    message: str
    count: int = 0
    out_path: Optional[str] = None


def _get_latest_curated_shas(conn: sqlite3.Connection, limit: int) -> list[str]:
    rows = conn.execute(
        "SELECT current_sha256 FROM fhir_curated_resource ORDER BY last_seen_ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [r[0] for r in rows if r and r[0]]


def _get_resource_json_by_sha(conn: sqlite3.Connection, sha: str) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT resource_json FROM fhir_raw_resource WHERE resource_sha256=? ORDER BY first_seen_ts DESC LIMIT 1",
        (sha,),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def export_curated_bundle_json(conn: sqlite3.Connection, out_path: str, limit: int = 500) -> ExportResult:
    shas = _get_latest_curated_shas(conn, limit)
    entries: list[dict[str, Any]] = []
    for sha in shas:
        res = _get_resource_json_by_sha(conn, sha)
        if isinstance(res, dict) and res.get("resourceType"):
            entries.append({"resource": res})
    bundle = {"resourceType": "Bundle", "type": "collection", "entry": entries}
    Path(out_path).write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return ExportResult(True, f"Exported {len(entries)} resources to {out_path}", count=len(entries), out_path=out_path)


# -------------------------
# Best-effort XML serializer
# -------------------------

def _xml_primitive(el: ET.Element, value: Any) -> None:
    # FHIR XML primitives use value=""
    el.set("value", str(value))


def _json_to_fhir_xml(parent: ET.Element, key: str, value: Any) -> None:
    # Generic conversion: for dict => nested elements, list => repeated elements, primitives => value=""
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            _json_to_fhir_xml(parent, key, item)
        return

    el = ET.SubElement(parent, f"{{{FHIR_NS}}}{key}")

    if isinstance(value, dict):
        for k, v in value.items():
            _json_to_fhir_xml(el, k, v)
    else:
        _xml_primitive(el, value)


def _resource_dict_to_xml(resource: dict[str, Any]) -> ET.Element:
    rt = resource.get("resourceType")
    if not isinstance(rt, str) or not rt:
        rt = "Resource"
    root = ET.Element(f"{{{FHIR_NS}}}{rt}")
    for k, v in resource.items():
        if k == "resourceType":
            continue
        _json_to_fhir_xml(root, k, v)
    return root


def export_curated_bundle_xml(conn: sqlite3.Connection, out_path: str, limit: int = 500, mode: str = "best-effort") -> ExportResult:
    """Export curated resources as FHIR Bundle XML.

    mode:
      - best-effort: generic serializer for any resource
      - strict: validator-oriented subset (Bundle/Patient/Observation) + rejects unknown fields
    """
    from mdr_gtk.fhir_xml import resource_to_xml_element, XmlBuildResult

    shas = _get_latest_curated_shas(conn, limit)

    # Build Bundle JSON first (so XML serializer can handle Bundle.entry ordering)
    entries = []
    for sha in shas:
        res = _get_resource_json_by_sha(conn, sha)
        if isinstance(res, dict) and res.get("resourceType"):
            entries.append({"resource": res})
    bundle_json = {"resourceType": "Bundle", "type": "collection", "entry": entries}

    built = resource_to_xml_element(bundle_json, mode=mode)
    if not built.ok or built.element is None:
        return ExportResult(False, built.message, count=0, out_path=out_path)

    tree = ET.ElementTree(built.element)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return ExportResult(True, f"Exported {len(entries)} resources to {out_path} (mode={mode})", count=len(entries), out_path=out_path)

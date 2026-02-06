from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Tuple

import sqlite3
import sys


CONFORMANCE_TYPES = {
    "StructureDefinition","ValueSet","CodeSystem","ImplementationGuide","CapabilityStatement",
    "OperationDefinition","SearchParameter","CompartmentDefinition","MessageDefinition",
    "ActivityDefinition","PlanDefinition","Measure","Questionnaire"
}


def stable_json(obj: Any) -> str:
    # Deterministic JSON serialization for stable SHA
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def iter_json_bundle_resources(bundle: dict[str, Any]) -> Iterable[Tuple[Optional[str], dict[str, Any]]]:
    for entry in (bundle.get("entry") or []):
        if not isinstance(entry, dict):
            continue
        res = entry.get("resource")
        if isinstance(res, dict) and res.get("resourceType"):
            yield entry.get("fullUrl"), res


def ref_edges(obj: Any, base_path: str = "") -> Iterable[Tuple[str, str]]:
    # yields (path, reference_string) for dicts with {"reference": "..."}
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{base_path}.{k}" if base_path else k
            if k == "reference" and isinstance(v, str):
                yield (base_path, v)
            else:
                yield from ref_edges(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{base_path}[{i}]"
            yield from ref_edges(v, p)


@dataclass
class ImportResult:
    ok: bool
    message: str
    run_id: Optional[int] = None
    raw_count: int = 0


def _new_run(conn: sqlite3.Connection, source_name: str, source_kind: str, partition_key: Optional[str]) -> int:
    cur = conn.execute(
        "INSERT INTO fhir_ingest_run(source_name, source_kind, fhir_major, partition_key) VALUES (?,?,?,?)",
        (source_name, source_kind, "R4", partition_key),
    )
    return int(cur.lastrowid)


def _finish_run(conn: sqlite3.Connection, run_id: int) -> None:
    conn.execute("UPDATE fhir_ingest_run SET finished_ts=(strftime('%Y-%m-%dT%H:%M:%fZ','now')) WHERE run_id=?", (run_id,))
    conn.commit()


def _insert_bundle(conn: sqlite3.Connection, run_id: int, bundle: dict[str, Any]) -> int:
    bjson = json.dumps(bundle, ensure_ascii=False)
    bsha = sha256_text(stable_json(bundle))
    btype = bundle.get("type")
    cur = conn.execute(
        "INSERT INTO fhir_raw_bundle(run_id, bundle_type, bundle_sha256, bundle_json) VALUES (?,?,?,?)",
        (run_id, btype, bsha, bjson),
    )
    return int(cur.lastrowid)


def _identity_key(resource_type: str, logical_id: Optional[str], canonical_url: Optional[str], artifact_version: Optional[str], partition_key: Optional[str]):
    # prefer canonical identity for conformance artifacts (url+version), else logical id
    if canonical_url:
        return ("canonical", resource_type, canonical_url, artifact_version or "", partition_key or "")
    return ("logical", resource_type, logical_id or "", partition_key or "")


def _find_curated(conn: sqlite3.Connection, key):
    if key[0] == "canonical":
        _, rt, url, ver, part = key
        return conn.execute(
            """SELECT curated_id, current_sha256 FROM fhir_curated_resource
                 WHERE resource_type=? AND canonical_url=? AND IFNULL(artifact_version,'')=? AND IFNULL(partition_key,'')=?""",
            (rt, url, ver, part),
        ).fetchone()
    else:
        _, rt, lid, part = key
        return conn.execute(
            """SELECT curated_id, current_sha256 FROM fhir_curated_resource
                 WHERE resource_type=? AND logical_id=? AND IFNULL(partition_key,'')=?""",
            (rt, lid, part),
        ).fetchone()


def _create_curated(conn: sqlite3.Connection, resource_type: str, logical_id: Optional[str], canonical_url: Optional[str], artifact_version: Optional[str],
                    partition_key: Optional[str], current_sha256: str) -> int:
    cur = conn.execute(
        """INSERT INTO fhir_curated_resource(
              resource_type, logical_id, canonical_url, artifact_version, partition_key,
              current_sha256, has_conflict
            ) VALUES (?,?,?,?,?,?,0)""",
        (resource_type, logical_id, canonical_url, artifact_version, partition_key, current_sha256),
    )
    return int(cur.lastrowid)


def _upsert_variant(conn: sqlite3.Connection, curated_id: int, sha: str, run_id: int) -> None:
    row = conn.execute(
        "SELECT occurrences FROM fhir_curated_variant WHERE curated_id=? AND resource_sha256=?",
        (curated_id, sha),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE fhir_curated_variant SET occurrences=occurrences+1, last_seen_run_id=? WHERE curated_id=? AND resource_sha256=?",
            (run_id, curated_id, sha),
        )
    else:
        conn.execute(
            "INSERT INTO fhir_curated_variant(curated_id, resource_sha256, occurrences, first_seen_run_id, last_seen_run_id) VALUES (?,?,?,?,?)",
            (curated_id, sha, 1, run_id, run_id),
        )


def import_fhir_bundle_json(
    conn: sqlite3.Connection,
    bundle: dict[str, Any],
    *,
    source_name: str = "bundle",
    partition_key: Optional[str] = None,
    extract_references: bool = True,
) -> ImportResult:
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        return ImportResult(False, "Not a FHIR Bundle JSON object")

    run_id = _new_run(conn, source_name=source_name, source_kind="bundle", partition_key=partition_key)
    try:
        bundle_id = _insert_bundle(conn, run_id, bundle)
        raw_n = 0

        for full_url, res in iter_json_bundle_resources(bundle):
            rt = str(res.get("resourceType"))
            logical_id = res.get("id") if isinstance(res.get("id"), str) else None
            canonical_url = res.get("url") if isinstance(res.get("url"), str) else None
            artifact_version = res.get("version") if isinstance(res.get("version"), str) else None

            meta = res.get("meta") if isinstance(res.get("meta"), dict) else {}
            meta_version_id = meta.get("versionId") if isinstance(meta.get("versionId"), str) else None
            meta_last_updated = meta.get("lastUpdated") if isinstance(meta.get("lastUpdated"), str) else None

            rjson = json.dumps(res, ensure_ascii=False)
            sha = sha256_text(stable_json(res))

            cur = conn.execute(
                """INSERT INTO fhir_raw_resource(
                    run_id, bundle_id, full_url,
                    resource_type, logical_id, canonical_url, artifact_version,
                    meta_version_id, meta_last_updated,
                    resource_sha256, resource_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, bundle_id, full_url,
                    rt, logical_id, canonical_url, artifact_version,
                    meta_version_id, meta_last_updated,
                    sha, rjson,
                ),
            )
            raw_id = int(cur.lastrowid)

            key = _identity_key(rt, logical_id, canonical_url, artifact_version, partition_key)
            found = _find_curated(conn, key)
            if found:
                curated_id, current_sha = int(found[0]), found[1]
                _upsert_variant(conn, curated_id, sha, run_id)
                # conflict if new sha differs
                if current_sha != sha:
                    conn.execute("UPDATE fhir_curated_resource SET has_conflict=1 WHERE curated_id=?", (curated_id,))
                conn.execute(
                    "UPDATE fhir_curated_resource SET last_seen_ts=(strftime('%Y-%m-%dT%H:%M:%fZ','now')) WHERE curated_id=?",
                    (curated_id,),
                )
            else:
                curated_id = _create_curated(conn, rt, logical_id, canonical_url, artifact_version, partition_key, sha)
                conn.execute(
                    "INSERT INTO fhir_curated_variant(curated_id, resource_sha256, occurrences, first_seen_run_id, last_seen_run_id) VALUES (?,?,?,?,?)",
                    (curated_id, sha, 1, run_id, run_id),
                )

            conn.execute(
                "INSERT OR REPLACE INTO fhir_raw_to_curated(raw_id, curated_id) VALUES (?,?)",
                (raw_id, curated_id),
            )

            if extract_references:
                for path, ref in ref_edges(res):
                    conn.execute(
                        "INSERT INTO fhir_reference_edge(run_id, from_raw_id, from_path, to_reference) VALUES (?,?,?,?)",
                        (run_id, raw_id, path, ref),
                    )

            raw_n += 1

        conn.commit()
        _finish_run(conn, run_id)
        return ImportResult(True, f"Imported FHIR Bundle: run_id={run_id}, resources={raw_n}", run_id=run_id, raw_count=raw_n)

    except Exception as e:
        conn.rollback()
        return ImportResult(False, f"Import failed: {e}", run_id=run_id, raw_count=0)

import tarfile
import tempfile
from pathlib import Path

def iter_package_json_files(root: Path) -> list[Path]:
    files = []
    for p in root.rglob("*.json"):
        if p.name in ("package.json", ".index.json"):
            continue
        files.append(p)
    return files


def _extract_tgz_to_temp(tgz_path: Path):
    """Extract tgz to a TemporaryDirectory and return (root_path, tmpdir).

    Keeping the TemporaryDirectory object alive prevents automatic cleanup
    during the import.
    """
    td = tempfile.TemporaryDirectory()
    out = Path(td.name)
    with tarfile.open(tgz_path, "r:*") as tf:
        if sys.version_info >= (3, 12):
            tf.extractall(out, filter="data")
        else:
            tf.extractall(out)
    # npm packages usually have "package/"
    root = out / "package" if (out / "package").exists() else out
    return root, td



def import_fhir_package(
    conn: sqlite3.Connection,
    package_path: str,
    *,
    source_name: str = "package",
    partition_key: Optional[str] = None,
    extract_references: bool = False,
) -> ImportResult:
    """Import a FHIR NPM package (.tgz/.tar.gz) or an unpacked directory.

    - imports all JSON resources with a `resourceType`
    - if a JSON file is a Bundle, imports its entries as resources
    - reference extraction is optional (default off for packages)
    """
    p = Path(package_path)
    if not p.exists():
        return ImportResult(False, f"Missing package path: {p}")

    run_id = _new_run(conn, source_name=source_name, source_kind="package", partition_key=partition_key)
    try:
        root = p
        if p.is_file() and (p.suffix in (".tgz", ".gz") or p.name.endswith(".tar.gz")):
            root, _td = _extract_tgz_to_temp(p)

        files = iter_package_json_files(root)
        raw_n = 0

        for fp in files:
            try:
                obj = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(obj, dict) or not obj.get("resourceType"):
                continue

            if obj.get("resourceType") == "Bundle":
                # treat bundles inside package as a bundle source, but keep run_id kind=package
                for full_url, res in iter_json_bundle_resources(obj):
                    rt = str(res.get("resourceType"))
                    logical_id = res.get("id") if isinstance(res.get("id"), str) else None
                    canonical_url = res.get("url") if isinstance(res.get("url"), str) else None
                    artifact_version = res.get("version") if isinstance(res.get("version"), str) else None

                    meta = res.get("meta") if isinstance(res.get("meta"), dict) else {}
                    meta_version_id = meta.get("versionId") if isinstance(meta.get("versionId"), str) else None
                    meta_last_updated = meta.get("lastUpdated") if isinstance(meta.get("lastUpdated"), str) else None

                    rjson = json.dumps(res, ensure_ascii=False)
                    sha = sha256_text(stable_json(res))

                    cur = conn.execute(
                        """INSERT INTO fhir_raw_resource(
                            run_id, bundle_id, full_url,
                            resource_type, logical_id, canonical_url, artifact_version,
                            meta_version_id, meta_last_updated,
                            resource_sha256, resource_json
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            run_id, None, full_url,
                            rt, logical_id, canonical_url, artifact_version,
                            meta_version_id, meta_last_updated,
                            sha, rjson,
                        ),
                    )
                    raw_id = int(cur.lastrowid)

                    key = _identity_key(rt, logical_id, canonical_url, artifact_version, partition_key)
                    found = _find_curated(conn, key)
                    if found:
                        curated_id, current_sha = int(found[0]), found[1]
                        _upsert_variant(conn, curated_id, sha, run_id)
                        if current_sha != sha:
                            conn.execute("UPDATE fhir_curated_resource SET has_conflict=1 WHERE curated_id=?", (curated_id,))
                        conn.execute(
                            "UPDATE fhir_curated_resource SET last_seen_ts=(strftime('%Y-%m-%dT%H:%M:%fZ','now')) WHERE curated_id=?",
                            (curated_id,),
                        )
                    else:
                        curated_id = _create_curated(conn, rt, logical_id, canonical_url, artifact_version, partition_key, sha)
                        conn.execute(
                            "INSERT INTO fhir_curated_variant(curated_id, resource_sha256, occurrences, first_seen_run_id, last_seen_run_id) VALUES (?,?,?,?,?)",
                            (curated_id, sha, 1, run_id, run_id),
                        )

                    conn.execute(
                        "INSERT OR REPLACE INTO fhir_raw_to_curated(raw_id, curated_id) VALUES (?,?)",
                        (raw_id, curated_id),
                    )

                    if extract_references:
                        for path, ref in ref_edges(res):
                            conn.execute(
                                "INSERT INTO fhir_reference_edge(run_id, from_raw_id, from_path, to_reference) VALUES (?,?,?,?)",
                                (run_id, raw_id, path, ref),
                            )
                    raw_n += 1
                continue

            # normal resource
            rt = str(obj.get("resourceType"))
            logical_id = obj.get("id") if isinstance(obj.get("id"), str) else None
            canonical_url = obj.get("url") if isinstance(obj.get("url"), str) else None
            artifact_version = obj.get("version") if isinstance(obj.get("version"), str) else None

            meta = obj.get("meta") if isinstance(obj.get("meta"), dict) else {}
            meta_version_id = meta.get("versionId") if isinstance(meta.get("versionId"), str) else None
            meta_last_updated = meta.get("lastUpdated") if isinstance(meta.get("lastUpdated"), str) else None

            rjson = json.dumps(obj, ensure_ascii=False)
            sha = sha256_text(stable_json(obj))

            cur = conn.execute(
                """INSERT INTO fhir_raw_resource(
                    run_id, bundle_id, full_url,
                    resource_type, logical_id, canonical_url, artifact_version,
                    meta_version_id, meta_last_updated,
                    resource_sha256, resource_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, None, None,
                    rt, logical_id, canonical_url, artifact_version,
                    meta_version_id, meta_last_updated,
                    sha, rjson,
                ),
            )
            raw_id = int(cur.lastrowid)

            key = _identity_key(rt, logical_id, canonical_url, artifact_version, partition_key)
            found = _find_curated(conn, key)
            if found:
                curated_id, current_sha = int(found[0]), found[1]
                _upsert_variant(conn, curated_id, sha, run_id)
                if current_sha != sha:
                    conn.execute("UPDATE fhir_curated_resource SET has_conflict=1 WHERE curated_id=?", (curated_id,))
                conn.execute(
                    "UPDATE fhir_curated_resource SET last_seen_ts=(strftime('%Y-%m-%dT%H:%M:%fZ','now')) WHERE curated_id=?",
                    (curated_id,),
                )
            else:
                curated_id = _create_curated(conn, rt, logical_id, canonical_url, artifact_version, partition_key, sha)
                conn.execute(
                    "INSERT INTO fhir_curated_variant(curated_id, resource_sha256, occurrences, first_seen_run_id, last_seen_run_id) VALUES (?,?,?,?,?)",
                    (curated_id, sha, 1, run_id, run_id),
                )

            conn.execute(
                "INSERT OR REPLACE INTO fhir_raw_to_curated(raw_id, curated_id) VALUES (?,?)",
                (raw_id, curated_id),
            )

            if extract_references:
                for path, ref in ref_edges(obj):
                    conn.execute(
                        "INSERT INTO fhir_reference_edge(run_id, from_raw_id, from_path, to_reference) VALUES (?,?,?,?)",
                        (run_id, raw_id, path, ref),
                    )

            raw_n += 1

        conn.commit()
        _finish_run(conn, run_id)
        return ImportResult(True, f"Imported FHIR package: run_id={run_id}, resources={raw_n}, files={len(files)}", run_id=run_id, raw_count=raw_n)

    except Exception as e:
        conn.rollback()
        return ImportResult(False, f"Package import failed: {e}", run_id=run_id, raw_count=0)
# --- XML support (Bundle import) ---------------------------------------------
import xml.etree.ElementTree as ET

FHIR_NS = "http://hl7.org/fhir"


def _ln(tag: str) -> str:
    """Localname of an XML tag."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _find_child(elem: Optional[ET.Element], name: str) -> Optional[ET.Element]:
    """Find first child with localname == name (FHIR namespace tolerant)."""
    if elem is None:
        return None
    for ch in list(elem):
        if _ln(ch.tag) == name:
            return ch
    return None


def _attr_value(elem: Optional[ET.Element]) -> Optional[str]:
    """FHIR XML uses value=... for primitives."""
    if elem is None:
        return None
    v = elem.attrib.get("value")
    return v if isinstance(v, str) else None


def _extract_resource_fields_from_xml(
    res_elem: ET.Element,
) -> tuple[str, Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Return (resource_type, logical_id, canonical_url, artifact_version, meta_version_id, meta_last_updated)
    from a FHIR XML resource element.
    """
    rt = _ln(res_elem.tag)

    logical_id = _attr_value(_find_child(res_elem, "id"))
    canonical_url = _attr_value(_find_child(res_elem, "url"))
    artifact_version = _attr_value(_find_child(res_elem, "version"))

    meta = _find_child(res_elem, "meta")
    meta_version_id = _attr_value(_find_child(meta, "versionId")) if meta is not None else None
    meta_last_updated = _attr_value(_find_child(meta, "lastUpdated")) if meta is not None else None

    return rt, logical_id, canonical_url, artifact_version, meta_version_id, meta_last_updated


def iter_xml_bundle_resources(xml_text: str) -> Iterable[tuple[Optional[str], ET.Element, str]]:
    """
    Yield (full_url, resource_element, resource_xml_text) for each Bundle.entry.resource.<X>.
    """
    root = ET.fromstring(xml_text)

    if _ln(root.tag) != "Bundle":
        return

    # Bundle.entry is namespaced
    for entry in root.findall(f".//{{{FHIR_NS}}}entry"):
        full_url = _attr_value(_find_child(entry, "fullUrl"))
        res_container = _find_child(entry, "resource")
        if res_container is None:
            continue

        children = list(res_container)
        if not children:
            continue
        res_elem = children[0]

        res_xml = ET.tostring(res_elem, encoding="unicode")
        yield full_url, res_elem, res_xml


def import_fhir_bundle_xml(
    conn: sqlite3.Connection,
    xml_text: str,
    *,
    source_name: str = "bundle-xml",
    partition_key: Optional[str] = None,
    extract_references: bool = True,
) -> ImportResult:
    """
    Import a FHIR Bundle from XML text.
    Stores raw resource payload as XML string in fhir_raw_resource.resource_json.
    Reference extraction for XML is currently skipped (future enhancement).
    """
    if not isinstance(xml_text, str) or not xml_text.strip():
        return ImportResult(False, "Empty XML input")

    run_id = _new_run(conn, source_name=source_name, source_kind="bundle", partition_key=partition_key)
    try:
        # Best-effort bundle_type extraction
        bundle_type = "collection"
        try:
            root = ET.fromstring(xml_text)
            if _ln(root.tag) == "Bundle":
                bt = _attr_value(_find_child(root, "type"))
                if bt:
                    bundle_type = bt
        except Exception:
            bundle_type = "collection"

        bsha = sha256_text(xml_text.strip())
        cur = conn.execute(
            "INSERT INTO fhir_raw_bundle(run_id, bundle_type, bundle_sha256, bundle_json) VALUES (?,?,?,?)",
            (run_id, bundle_type, bsha, xml_text),
        )
        bundle_id = int(cur.lastrowid)

        raw_n = 0

        for full_url, res_elem, res_xml in iter_xml_bundle_resources(xml_text):
            rt, logical_id, canonical_url, artifact_version, meta_version_id, meta_last_updated = _extract_resource_fields_from_xml(res_elem)
            if not rt:
                continue

            sha = sha256_text(res_xml.strip())

            cur = conn.execute(
                """INSERT INTO fhir_raw_resource(
                    run_id, bundle_id, full_url,
                    resource_type, logical_id, canonical_url, artifact_version,
                    meta_version_id, meta_last_updated,
                    resource_sha256, resource_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, bundle_id, full_url,
                    rt, logical_id, canonical_url, artifact_version,
                    meta_version_id, meta_last_updated,
                    sha, res_xml,
                ),
            )
            raw_id = int(cur.lastrowid)

            key = _identity_key(rt, logical_id, canonical_url, artifact_version, partition_key)
            found = _find_curated(conn, key)

            if found:
                curated_id, current_sha = int(found[0]), found[1]
                _upsert_variant(conn, curated_id, sha, run_id)
                if current_sha != sha:
                    conn.execute("UPDATE fhir_curated_resource SET has_conflict=1 WHERE curated_id=?", (curated_id,))
                conn.execute(
                    "UPDATE fhir_curated_resource SET last_seen_ts=(strftime('%Y-%m-%dT%H:%M:%fZ','now')) WHERE curated_id=?",
                    (curated_id,),
                )
            else:
                curated_id = _create_curated(conn, rt, logical_id, canonical_url, artifact_version, partition_key, sha)
                conn.execute(
                    "INSERT INTO fhir_curated_variant(curated_id, resource_sha256, occurrences, first_seen_run_id, last_seen_run_id) VALUES (?,?,?,?,?)",
                    (curated_id, sha, 1, run_id, run_id),
                )

            conn.execute(
                "INSERT OR REPLACE INTO fhir_raw_to_curated(raw_id, curated_id) VALUES (?,?)",
                (raw_id, curated_id),
            )

            raw_n += 1

        conn.commit()
        _finish_run(conn, run_id)
        return ImportResult(True, f"Imported FHIR Bundle XML: run_id={run_id}, resources={raw_n}", run_id=run_id, raw_count=raw_n)

    except Exception as e:
        conn.rollback()
        return ImportResult(False, f"Import failed: {e}", run_id=run_id, raw_count=0)

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CuratedInfo:
    curated_id: int
    resource_type: str
    canonical_or_id: str
    artifact_version: str
    current_sha256: str
    has_conflict: int


def get_curated_by_ident(conn: sqlite3.Connection, ident: str) -> Optional[CuratedInfo]:
    """Lookup curated resource by canonical_url or logical_id string (shown in GUI)."""
    row = conn.execute(
        "SELECT curated_id, resource_type, IFNULL(canonical_url, logical_id), IFNULL(artifact_version,''), current_sha256, has_conflict "
        "FROM fhir_curated_resource WHERE IFNULL(canonical_url, logical_id)=? LIMIT 1",
        (ident,),
    ).fetchone()
    if not row:
        return None
    return CuratedInfo(
        curated_id=int(row[0]),
        resource_type=str(row[1]),
        canonical_or_id=str(row[2]),
        artifact_version=str(row[3]),
        current_sha256=str(row[4]),
        has_conflict=int(row[5]),
    )


def get_variants_for_curated(conn: sqlite3.Connection, curated_id: int, limit: int = 50) -> list[tuple[str, int]]:
    rows = conn.execute(
        "SELECT resource_sha256, occurrences FROM fhir_curated_variant WHERE curated_id=? "
        "ORDER BY occurrences DESC LIMIT ?",
        (curated_id, limit),
    ).fetchall()
    return [(str(r[0]), int(r[1])) for r in rows]


def get_raw_json_by_sha(conn: sqlite3.Connection, sha: str) -> Optional[dict[str, Any]]:
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

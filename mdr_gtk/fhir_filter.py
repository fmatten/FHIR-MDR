from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CuratedFilter:
    resource_type: str | None = None   # None or "All"
    text: str | None = None            # substring match on canonical_url or logical_id
    conflicts_only: bool = False
    limit: int = 500


def build_curated_query(f: CuratedFilter) -> tuple[str, list[Any]]:
    """Return SQL + params for curated list view.

    Filters:
    - resource_type: exact match
    - text: case-insensitive substring on canonical_url/logical_id
    - conflicts_only: has_conflict=1
    """
    where = []
    params: list[Any] = []

    if f.resource_type and f.resource_type.lower() not in ("all", "*"):
        where.append("resource_type = ?")
        params.append(f.resource_type)

    if f.text and f.text.strip():
        # SQLite LIKE is case-insensitive for ASCII by default; use lower() for robustness
        where.append("(lower(IFNULL(canonical_url,'')) LIKE ? OR lower(IFNULL(logical_id,'')) LIKE ?)")
        t = "%" + f.text.strip().lower() + "%"
        params.extend([t, t])

    if f.conflicts_only:
        where.append("has_conflict = 1")

    sql = (
        "SELECT resource_type, IFNULL(canonical_url, logical_id) as ident, IFNULL(artifact_version,'') as ver, "
        "has_conflict, last_seen_ts "
        "FROM fhir_curated_resource"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY last_seen_ts DESC LIMIT ?"
    params.append(int(f.limit))
    return sql, params

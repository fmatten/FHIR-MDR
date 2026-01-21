"""
Export to SKOS (Turtle).
- Classification schemes -> skos:ConceptScheme
- Classification items -> skos:Concept (+ broader)
- All registrable_item -> skos:Concept in a generic scheme urn:mdr:items
- Designations -> skos:prefLabel / skos:altLabel
- Item classifications -> dcterms:subject linking item-concepts to classification concepts
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from mdr_gtk.db import connect


def ttl_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def iri(base: str, uuid: str) -> str:
    # base should end with ':' or '/' etc; keep as-is.
    return f"{base}{uuid}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="mdr.sqlite")
    p.add_argument("--out", required=True)
    p.add_argument("--base", default="urn:mdr:", help="Base IRI prefix for resources (e.g. urn:example:mdr:)")
    args = p.parse_args()

    conn = connect(args.db)
    try:
        base = args.base

        out_lines = []
        out_lines.append("@prefix skos: <http://www.w3.org/2004/02/skos/core#> .")
        out_lines.append("@prefix dcterms: <http://purl.org/dc/terms/> .")
        out_lines.append("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .")
        out_lines.append("")

        # Generic scheme for all items
        scheme_items = "urn:mdr:items"
        out_lines.append(f"<{scheme_items}> a skos:ConceptScheme ; skos:prefLabel \"MDR Items\"@en .")
        out_lines.append("")

        # Classification schemes
        schemes = conn.execute(
            """
            SELECT ri.uuid, ri.preferred_name, ri.definition, cs.scheme_uri
            FROM classification_scheme cs
            JOIN registrable_item ri ON ri.uuid = cs.uuid
            """
        ).fetchall()

        for s in schemes:
            s_iri = iri(base, s["uuid"])
            label = ttl_escape(s["preferred_name"])
            definition = ttl_escape(s["definition"])
            out_lines.append(f"<{s_iri}> a skos:ConceptScheme ;")
            out_lines.append(f"  skos:prefLabel \"{label}\"@en ;")
            out_lines.append(f"  skos:definition \"{definition}\"@en ;")
            if s["scheme_uri"]:
                out_lines.append(f"  dcterms:identifier \"{ttl_escape(s['scheme_uri'])}\" ;")
            out_lines[-1] = out_lines[-1].rstrip(" ;") + " ."
            out_lines.append("")

        # Classification items as concepts
        cis = conn.execute(
            """
            SELECT ri.uuid, ri.preferred_name, ri.definition, ci.scheme_uuid, ci.parent_uuid, ci.item_code
            FROM classification_item ci
            JOIN registrable_item ri ON ri.uuid = ci.uuid
            """
        ).fetchall()

        for c in cis:
            c_iri = iri(base, c["uuid"])
            label = ttl_escape(c["preferred_name"])
            definition = ttl_escape(c["definition"])
            scheme_iri = iri(base, c["scheme_uuid"])
            out_lines.append(f"<{c_iri}> a skos:Concept ;")
            out_lines.append(f"  skos:inScheme <{scheme_iri}> ;")
            out_lines.append(f"  skos:prefLabel \"{label}\"@en ;")
            out_lines.append(f"  skos:definition \"{definition}\"@en ;")
            if c["item_code"]:
                out_lines.append(f"  dcterms:identifier \"{ttl_escape(c['item_code'])}\" ;")
            if c["parent_uuid"]:
                out_lines.append(f"  skos:broader <{iri(base, c['parent_uuid'])}> ;")
            out_lines[-1] = out_lines[-1].rstrip(" ;") + " ."
            out_lines.append("")

        # All registrable items as concepts
        items = conn.execute("SELECT uuid, item_type, preferred_name, definition FROM registrable_item").fetchall()
        for it in items:
            it_iri = iri(base, it["uuid"])
            label = ttl_escape(it["preferred_name"])
            definition = ttl_escape(it["definition"])
            out_lines.append(f"<{it_iri}> a skos:Concept ;")
            out_lines.append(f"  skos:inScheme <{scheme_items}> ;")
            out_lines.append(f"  skos:prefLabel \"{label}\"@en ;")
            out_lines.append(f"  skos:definition \"{definition}\"@en ;")
            out_lines.append(f"  dcterms:type \"{ttl_escape(it['item_type'])}\" ;")
            out_lines[-1] = out_lines[-1].rstrip(" ;") + " ."
            out_lines.append("")

        # Designations as labels
        des = conn.execute(
            """
            SELECT d.item_uuid, d.language_tag, d.designation, d.designation_type, d.is_preferred
            FROM designation d
            """
        ).fetchall()
        for d in des:
            subj = f"<{iri(base, d['item_uuid'])}>"
            lang = d["language_tag"] or "und"
            text = ttl_escape(d["designation"])
            if d["designation_type"] == "preferred" or d["is_preferred"] == 1:
                pred = "skos:prefLabel"
            else:
                pred = "skos:altLabel"
            out_lines.append(f"{subj} {pred} \"{text}\"@{lang} .")

        out_lines.append("")

        # Item classifications -> dcterms:subject (item concept -> classification concept)
        ics = conn.execute(
            """
            SELECT item_uuid, classification_item_uuid
            FROM item_classification
            """
        ).fetchall()
        for ic in ics:
            out_lines.append(f"<{iri(base, ic['item_uuid'])}> dcterms:subject <{iri(base, ic['classification_item_uuid'])}> .")

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(out_lines), encoding="utf-8")
        print(f"OK: Exported SKOS TTL {out.resolve()}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

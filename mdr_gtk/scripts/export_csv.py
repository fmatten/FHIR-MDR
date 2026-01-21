"""
Export registrable items to a single CSV for quick interchange.

Entity-specific fields are flattened when possible; otherwise left blank.
Permissible values and designations are NOT included in this CSV (use JSON for full fidelity).
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from mdr_gtk.db import connect


FIELDS = [
    "uuid","item_type","preferred_name","definition",
    "context_uuid","registration_authority_uuid",
    "registration_status","administrative_status",
    "steward","submitting_organization","version",
    "created_at","updated_at",
    # common optional joins
    "vd_datatype","vd_unit_of_measure","vd_max_length","vd_format","vd_conceptual_domain_uuid","vd_representation_class_uuid",
    "dec_object_class_uuid","dec_property_uuid","dec_conceptual_domain_uuid",
    "de_data_element_concept_uuid","de_value_domain_uuid",
    "cs_scheme_uri",
    "ci_scheme_uuid","ci_parent_uuid","ci_item_code",
    "cd_description",
]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="mdr.sqlite")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    conn = connect(args.db)
    try:
        # Pull everything with left joins.
        rows = conn.execute(
            """
            SELECT
              ri.*,
              vd.datatype AS vd_datatype,
              vd.unit_of_measure AS vd_unit_of_measure,
              vd.max_length AS vd_max_length,
              vd.format AS vd_format,
              vd.conceptual_domain_uuid AS vd_conceptual_domain_uuid,
              vd.representation_class_uuid AS vd_representation_class_uuid,
              dec.object_class_uuid AS dec_object_class_uuid,
              dec.property_uuid AS dec_property_uuid,
              dec.conceptual_domain_uuid AS dec_conceptual_domain_uuid,
              de.data_element_concept_uuid AS de_data_element_concept_uuid,
              de.value_domain_uuid AS de_value_domain_uuid,
              cs.scheme_uri AS cs_scheme_uri,
              ci.scheme_uuid AS ci_scheme_uuid,
              ci.parent_uuid AS ci_parent_uuid,
              ci.item_code AS ci_item_code,
              cd.description AS cd_description
            FROM registrable_item ri
            LEFT JOIN value_domain vd ON vd.uuid = ri.uuid
            LEFT JOIN data_element_concept dec ON dec.uuid = ri.uuid
            LEFT JOIN data_element de ON de.uuid = ri.uuid
            LEFT JOIN classification_scheme cs ON cs.uuid = ri.uuid
            LEFT JOIN classification_item ci ON ci.uuid = ri.uuid
            LEFT JOIN conceptual_domain cd ON cd.uuid = ri.uuid
            ORDER BY ri.item_type, ri.preferred_name COLLATE NOCASE
            """
        ).fetchall()

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            for r in rows:
                d = {k: r[k] if k in r.keys() else None for k in FIELDS}
                writer.writerow(d)
        print(f"OK: Exported {out.resolve()}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

from __future__ import annotations

import sqlite3
import uuid as uuidlib
from typing import Any, Dict, List, Optional, Tuple

from mdr_gtk.models import RegistrableItem


def new_uuid(prefix: str) -> str:
    return f"{prefix}-{uuidlib.uuid4().hex[:12]}"


class Repo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ---------- shared: registrable_item ----------
    def create_item(self, item: RegistrableItem) -> None:
        self.conn.execute(
            """
            INSERT INTO registrable_item(
              uuid,item_type,preferred_name,definition,context_uuid,registration_authority_uuid,
              registration_status,administrative_status,steward,submitting_organization,version
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                item.uuid, item.item_type, item.preferred_name, item.definition,
                item.context_uuid, item.registration_authority_uuid,
                item.registration_status, item.administrative_status,
                item.steward, item.submitting_organization, item.version,
            ),
        )

    def update_item(self, item_uuid: str, fields: Dict[str, Any], change_note: str | None = None, changed_by: str | None = None) -> None:
        cur = self.conn.execute("SELECT version FROM registrable_item WHERE uuid=?", (item_uuid,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Item not found")
        old_version = int(row["version"])

        self.conn.execute(
            "INSERT INTO item_version(uuid,item_uuid,version,changed_by,change_note) VALUES(?,?,?,?,?)",
            (new_uuid("iv"), item_uuid, old_version, changed_by, change_note),
        )

        new_version = old_version + 1
        fields = dict(fields)
        fields["version"] = new_version

        cols = ", ".join([f"{k}=?" for k in fields.keys()])
        params = list(fields.values()) + [item_uuid]
        self.conn.execute(f"UPDATE registrable_item SET {cols} WHERE uuid=?", params)

    def delete_item(self, item_uuid: str) -> None:
        self.conn.execute("DELETE FROM registrable_item WHERE uuid=?", (item_uuid,))

    def list_items(self, item_type: str, q: str | None = None) -> List[sqlite3.Row]:
        if q:
            return list(self.conn.execute(
                """
                SELECT uuid, preferred_name, definition, registration_status, administrative_status, version, updated_at
                FROM registrable_item
                WHERE item_type=? AND (preferred_name LIKE ? OR definition LIKE ?)
                ORDER BY preferred_name COLLATE NOCASE
                """,
                (item_type, f"%{q}%", f"%{q}%"),
            ))
        return list(self.conn.execute(
            """
            SELECT uuid, preferred_name, definition, registration_status, administrative_status, version, updated_at
            FROM registrable_item
            WHERE item_type=?
            ORDER BY preferred_name COLLATE NOCASE
            """,
            (item_type,),
        ))

    def get_item(self, item_uuid: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM registrable_item WHERE uuid=?", (item_uuid,)).fetchone()

    def fetch_refs(self, item_type: str) -> List[Tuple[str, str]]:
        rows = self.conn.execute(
            "SELECT uuid, preferred_name FROM registrable_item WHERE item_type=? ORDER BY preferred_name COLLATE NOCASE",
            (item_type,),
        ).fetchall()
        return [(r["uuid"], r["preferred_name"]) for r in rows]

    # ---------- ensure entity rows (1:1 tables) ----------
    def ensure_row(self, table: str, uuid: str) -> None:
        self.conn.execute(f"INSERT OR IGNORE INTO {table}(uuid) VALUES(?)", (uuid,))

    # ---------- VD / DEC / DE ----------
    def upsert_value_domain(self, uuid: str, datatype: str, unit_of_measure: str | None, max_length: int | None,
                            format: str | None, conceptual_domain_uuid: str | None, representation_class_uuid: str | None) -> None:
        self.conn.execute(
            """
            INSERT INTO value_domain(uuid,datatype,unit_of_measure,max_length,format,conceptual_domain_uuid,representation_class_uuid)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(uuid) DO UPDATE SET
              datatype=excluded.datatype,
              unit_of_measure=excluded.unit_of_measure,
              max_length=excluded.max_length,
              format=excluded.format,
              conceptual_domain_uuid=excluded.conceptual_domain_uuid,
              representation_class_uuid=excluded.representation_class_uuid
            """,
            (uuid, datatype, unit_of_measure, max_length, format, conceptual_domain_uuid, representation_class_uuid),
        )

    def get_value_domain(self, uuid: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM value_domain WHERE uuid=?", (uuid,)).fetchone()

    def upsert_data_element_concept(self, uuid: str, object_class_uuid: str, property_uuid: str, conceptual_domain_uuid: str | None) -> None:
        self.conn.execute(
            """
            INSERT INTO data_element_concept(uuid,object_class_uuid,property_uuid,conceptual_domain_uuid)
            VALUES(?,?,?,?)
            ON CONFLICT(uuid) DO UPDATE SET
              object_class_uuid=excluded.object_class_uuid,
              property_uuid=excluded.property_uuid,
              conceptual_domain_uuid=excluded.conceptual_domain_uuid
            """,
            (uuid, object_class_uuid, property_uuid, conceptual_domain_uuid),
        )

    def get_data_element_concept(self, uuid: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM data_element_concept WHERE uuid=?", (uuid,)).fetchone()

    def upsert_data_element(self, uuid: str, dec_uuid: str, vd_uuid: str) -> None:
        self.conn.execute(
            """
            INSERT INTO data_element(uuid,data_element_concept_uuid,value_domain_uuid)
            VALUES(?,?,?)
            ON CONFLICT(uuid) DO UPDATE SET
              data_element_concept_uuid=excluded.data_element_concept_uuid,
              value_domain_uuid=excluded.value_domain_uuid
            """,
            (uuid, dec_uuid, vd_uuid),
        )

    def get_data_element(self, uuid: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM data_element WHERE uuid=?", (uuid,)).fetchone()

    # ---------- Designations ----------
    def list_designations(self, item_uuid: str) -> List[sqlite3.Row]:
        return list(self.conn.execute(
            """
            SELECT uuid, language_tag, designation_type, designation, is_preferred
            FROM designation
            WHERE item_uuid=?
            ORDER BY is_preferred DESC, designation_type, language_tag, designation COLLATE NOCASE
            """,
            (item_uuid,),
        ))

    def upsert_designation(self, des_uuid: str, item_uuid: str, context_uuid: str | None, language_tag: str,
                          designation_type: str, designation: str, is_preferred: int) -> None:
        self.conn.execute(
            """
            INSERT INTO designation(uuid,item_uuid,context_uuid,language_tag,designation_type,designation,is_preferred)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(uuid) DO UPDATE SET
              context_uuid=excluded.context_uuid,
              language_tag=excluded.language_tag,
              designation_type=excluded.designation_type,
              designation=excluded.designation,
              is_preferred=excluded.is_preferred
            """,
            (des_uuid, item_uuid, context_uuid, language_tag, designation_type, designation, int(is_preferred)),
        )

    def delete_designation(self, des_uuid: str) -> None:
        self.conn.execute("DELETE FROM designation WHERE uuid=?", (des_uuid,))

    # ---------- Permissible Values ----------
    def list_permissible_values(self, vd_uuid: str) -> List[sqlite3.Row]:
        return list(self.conn.execute(
            """
            SELECT uuid, code, meaning, sort_order
            FROM permissible_value
            WHERE value_domain_uuid=?
            ORDER BY COALESCE(sort_order, 999999), code COLLATE NOCASE
            """,
            (vd_uuid,),
        ))

    def upsert_permissible_value(self, pv_uuid: str, vd_uuid: str, code: str, meaning: str, sort_order: int | None) -> None:
        self.conn.execute(
            """
            INSERT INTO permissible_value(uuid,value_domain_uuid,code,meaning,sort_order)
            VALUES(?,?,?,?,?)
            ON CONFLICT(uuid) DO UPDATE SET
              value_domain_uuid=excluded.value_domain_uuid,
              code=excluded.code,
              meaning=excluded.meaning,
              sort_order=excluded.sort_order
            """,
            (pv_uuid, vd_uuid, code, meaning, sort_order),
        )

    def delete_permissible_value(self, pv_uuid: str) -> None:
        self.conn.execute("DELETE FROM permissible_value WHERE uuid=?", (pv_uuid,))

    # ---------- Classification ----------
    def upsert_classification_scheme(self, uuid: str, scheme_uri: str | None) -> None:
        self.conn.execute(
            """
            INSERT INTO classification_scheme(uuid,scheme_uri)
            VALUES(?,?)
            ON CONFLICT(uuid) DO UPDATE SET scheme_uri=excluded.scheme_uri
            """,
            (uuid, scheme_uri),
        )

    def get_classification_scheme(self, uuid: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM classification_scheme WHERE uuid=?", (uuid,)).fetchone()

    def upsert_classification_item(self, uuid: str, scheme_uuid: str, parent_uuid: str | None, item_code: str | None) -> None:
        self.conn.execute(
            """
            INSERT INTO classification_item(uuid,scheme_uuid,parent_uuid,item_code)
            VALUES(?,?,?,?)
            ON CONFLICT(uuid) DO UPDATE SET
              scheme_uuid=excluded.scheme_uuid,
              parent_uuid=excluded.parent_uuid,
              item_code=excluded.item_code
            """,
            (uuid, scheme_uuid, parent_uuid, item_code),
        )

    def get_classification_item(self, uuid: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM classification_item WHERE uuid=?", (uuid,)).fetchone()

    def list_item_classifications(self, item_uuid: str) -> List[sqlite3.Row]:
        return list(self.conn.execute(
            """
            SELECT ic.uuid as uuid,
                   ci.uuid as classification_item_uuid,
                   ri_ci.preferred_name as classification_item_name,
                   ri_cs.preferred_name as scheme_name
            FROM item_classification ic
            JOIN classification_item ci ON ci.uuid = ic.classification_item_uuid
            JOIN classification_scheme cs ON cs.uuid = ci.scheme_uuid
            JOIN registrable_item ri_ci ON ri_ci.uuid = ci.uuid
            JOIN registrable_item ri_cs ON ri_cs.uuid = cs.uuid
            WHERE ic.item_uuid=?
            ORDER BY scheme_name COLLATE NOCASE, classification_item_name COLLATE NOCASE
            """,
            (item_uuid,),
        ))

    def add_item_classification(self, item_uuid: str, classification_item_uuid: str, assigned_by: str | None) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO item_classification(uuid,item_uuid,classification_item_uuid,assigned_by)
            VALUES(?,?,?,?)
            """,
            (new_uuid("ic"), item_uuid, classification_item_uuid, assigned_by),
        )

    def delete_item_classification(self, ic_uuid: str) -> None:
        self.conn.execute("DELETE FROM item_classification WHERE uuid=?", (ic_uuid,))

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio
import json
import csv
from pathlib import Path

from mdr_gtk.db import connect
from mdr_gtk.services import ensure_schema_applied
from mdr_gtk.repositories import Repo, new_uuid
import json
from pathlib import Path
from mdr_gtk.fhir_ingest import import_fhir_bundle_json, import_fhir_package
from mdr_gtk.fhir_export import export_curated_bundle_json, export_curated_bundle_xml
from mdr_gtk.fhir_repo import get_curated_by_ident, get_variants_for_curated, get_raw_json_by_sha
from mdr_gtk.fhir_filter import CuratedFilter, build_curated_query
from mdr_gtk.fhir_selected_export import export_selected_bundle_json, export_selected_bundle_xml
from mdr_gtk.util import read_text

from mdr_gtk.models import RegistrableItem



class _RefDropDown:
    """Small helper that maps a Gtk.DropDown selection to UUID values.

    `options` is a list of (uuid, label) tuples.
    If `allow_none` is True, the first option is an empty selection.
    """

    def __init__(self, options, allow_none: bool = False, none_label: str = "—"):
        self.allow_none = allow_none
        self._uuids = []
        labels = []

        if allow_none:
            self._uuids.append(None)
            labels.append(none_label)

        for u, lbl in (options or []):
            self._uuids.append(u)
            labels.append(lbl or "")

        # Ensure the dropdown always has at least one row.
        if not labels:
            self._uuids = [None]
            labels = [none_label]

        self.widget = Gtk.DropDown.new_from_strings(labels)

        # Default selection:
        # - allow_none -> select the empty row
        # - otherwise -> select first real row (index 0)
        self.widget.set_selected(0)

    def get_selected_uuid(self):
        idx = int(self.widget.get_selected())
        if idx < 0 or idx >= len(self._uuids):
            return None
        return self._uuids[idx]

    def set_selected_uuid(self, uuid_value):
        # None handling
        if uuid_value is None:
            if self.allow_none:
                self.widget.set_selected(0)
            return

        try:
            idx = self._uuids.index(uuid_value)
        except ValueError:
            return
        self.widget.set_selected(idx)
ITEM_TYPES = [
    ("DATA_ELEMENT", "Data Elements"),
    ("DATA_ELEMENT_CONCEPT", "Data Element Concepts"),
    ("VALUE_DOMAIN", "Value Domains"),
    ("CONCEPTUAL_DOMAIN", "Conceptual Domains"),
    ("OBJECT_CLASS", "Object Classes"),
    ("PROPERTY", "Properties"),
    ("REPRESENTATION_CLASS", "Representation Classes"),
    ("CLASSIFICATION_SCHEME", "Classification Schemes"),
    ("CLASSIFICATION_ITEM", "Classification Items"),
]


class MDRWindow(Gtk.ApplicationWindow):

    def __init__(self, app: Gtk.Application, db_path: str, use_adwaita: bool = False):
        # Note: Gtk.ApplicationWindow must be initialized via keyword properties.
        super().__init__(application=app, title="ISO/IEC 11179 MDR (SQLite) – Core+")
        self.set_default_size(1200, 740)

        self.conn = connect(db_path)
        self._ensure_schema()
        self.repo = Repo(self.conn)
        self.db_path = db_path

        self.current_type = ITEM_TYPES[0][0]
        self.current_uuid: str | None = None
        self.log_lines: list[str] = []

        self._build_ui()
        self._refresh_list()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
        return super().close()

    def _ensure_schema(self) -> None:
        # Apply schema if not present (MDR + FHIR)
        ensure_schema_applied(self.conn)

    def _build_ui(self):
        hb = Gtk.HeaderBar()
        self.set_titlebar(hb)

        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Suche… (Name/Definition)")
        self.search.connect("search-changed", self._on_search_changed)
        hb.pack_start(self.search)


        # Menu (Import/Export)
        self.menu_btn = Gtk.MenuButton()
        self.menu_btn.set_label("☰")
        menu_model = Gio.Menu()
        menu_model.append("Open DB…", "app.open_db")
        menu_model.append("New DB…", "app.new_db")
        menu_model.append("Export JSON…", "app.export_json")
        menu_model.append("Import JSON…", "app.import_json")
        menu_model.append("Export CSV…", "app.export_csv")
        menu_model.append("Export SKOS (TTL)…", "app.export_skos")
        menu_model.append("FHIR: Import Bundle (JSON)…", "app.import_fhir_bundle")
        menu_model.append("FHIR: Import Package (.tgz)…", "app.import_fhir_package")
        menu_model.append("FHIR: Export Curated Bundle (JSON)…", "app.export_fhir_bundle_json")
        menu_model.append("FHIR: Export Curated Bundle (XML)…", "app.export_fhir_bundle_xml")
        self.menu_btn.set_menu_model(menu_model)
        hb.pack_end(self.menu_btn)


        self.btn_new = Gtk.Button(label="Neu")
        self.btn_new.connect("clicked", self._on_new)
        hb.pack_end(self.btn_new)

        self.btn_save = Gtk.Button(label="Speichern")
        self.btn_save.connect("clicked", self._on_save)
        hb.pack_end(self.btn_save)

        self.btn_delete = Gtk.Button(label="Löschen")
        self.btn_delete.connect("clicked", self._on_delete)
        hb.pack_end(self.btn_delete)

        root = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        # Notebook: MDR + FHIR
        self.notebook = Gtk.Notebook()
        self.notebook.set_hexpand(True)
        self.notebook.set_vexpand(True)
        
        self.notebook.append_page(root, Gtk.Label(label="MDR"))
        self.fhir_page = self._build_fhir_page()
        self.notebook.append_page(self.fhir_page, Gtk.Label(label="FHIR"))
        
        self.set_child(self.notebook)


        # Left: type navigation
        self.type_store = Gio.ListStore.new(Gtk.StringObject)
        for _t, label in ITEM_TYPES:
            self.type_store.append(Gtk.StringObject.new(label))

        self.type_selection = Gtk.SingleSelection.new(self.type_store)
        self.type_selection.connect("notify::selected", self._on_type_selected)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._type_setup)
        factory.connect("bind", self._type_bind)
        self.type_view = Gtk.ListView.new(self.type_selection, factory)
        self.type_view.set_vexpand(True)

        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        left_box.append(Gtk.Label(label="Objekte", xalign=0))
        left_box.append(self.type_view)
        root.set_start_child(left_box)

        # Middle: items list
        self.item_store = Gio.ListStore.new(Gtk.StringObject)
        self.item_selection = Gtk.SingleSelection.new(self.item_store)
        self.item_selection.connect("notify::selected", self._on_item_selected)

        item_factory = Gtk.SignalListItemFactory()
        item_factory.connect("setup", self._item_setup)
        item_factory.connect("bind", self._item_bind)

        self.item_view = Gtk.ListView.new(self.item_selection, item_factory)
        self.item_view.set_vexpand(True)

        mid_scroller = Gtk.ScrolledWindow()
        mid_scroller.set_child(self.item_view)

        mid_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        self.lbl_mid = Gtk.Label(label="Liste", xalign=0)
        mid_box.append(self.lbl_mid)
        mid_box.append(mid_scroller)

        root2 = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        root.set_end_child(root2)
        root2.set_start_child(mid_box)

        # Right: details editor
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.detail.set_vexpand(True)

        self.err = Gtk.Label(label="", xalign=0)
        self.err.add_css_class("error")
        self.detail.append(self.err)

        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        self.detail.append(grid)

        def add_row(r: int, label: str, widget: Gtk.Widget):
            l = Gtk.Label(label=label, xalign=0)
            grid.attach(l, 0, r, 1, 1)
            grid.attach(widget, 1, r, 1, 1)

        self.f_uuid = Gtk.Entry()
        self.f_uuid.set_editable(False)

        self.f_name = Gtk.Entry()
        self.f_def = Gtk.TextView()
        self.f_def.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        def_sc = Gtk.ScrolledWindow()
        def_sc.set_min_content_height(120)
        def_sc.set_child(self.f_def)

        self.f_reg_status = Gtk.DropDown.new_from_strings(["Candidate","Recorded","Qualified","Standard","Retired"])
        self.f_admin_status = Gtk.DropDown.new_from_strings(["Draft","Released","Superseded","Deprecated"])
        self.f_steward = Gtk.Entry()

        add_row(0, "UUID", self.f_uuid)
        add_row(1, "Preferred Name*", self.f_name)
        add_row(2, "Definition*", def_sc)
        add_row(3, "Registration Status", self.f_reg_status)
        add_row(4, "Administrative Status", self.f_admin_status)
        add_row(5, "Steward", self.f_steward)

        # entity specific
        self.detail.append(Gtk.Separator())
        self.extra = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.detail.append(self.extra)

        # designations
        self.detail.append(Gtk.Separator())
        self.detail.append(Gtk.Label(label="Designations (Language/Type)", xalign=0))
        self.des_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.detail.append(self.des_box)
        des_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.btn_des_add = Gtk.Button(label="Designation hinzufügen")
        self.btn_des_add.connect("clicked", self._on_des_add)
        self.btn_des_del = Gtk.Button(label="Ausgewählte Designation löschen")
        self.btn_des_del.connect("clicked", self._on_des_delete)
        des_btns.append(self.btn_des_add)
        des_btns.append(self.btn_des_del)
        self.detail.append(des_btns)

        # classifications (assignments)
        self.detail.append(Gtk.Separator())
        self.detail.append(Gtk.Label(label="Klassifikationen (Zuordnung)", xalign=0))
        self.ic_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.detail.append(self.ic_box)

        ic_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.ic_add_dd = None  # built on load
        self.btn_ic_add = Gtk.Button(label="Zuordnung hinzufügen")
        self.btn_ic_add.connect("clicked", self._on_ic_add)
        self.btn_ic_del = Gtk.Button(label="Ausgewählte Zuordnung löschen")
        self.btn_ic_del.connect("clicked", self._on_ic_delete)
        ic_btns.append(self.btn_ic_add)
        ic_btns.append(self.btn_ic_del)
        self.detail.append(ic_btns)

        # footer
        self.detail.append(Gtk.Separator())
        self.footer = Gtk.Label(label="", xalign=0)
        self.detail.append(self.footer)

        right_scroller = Gtk.ScrolledWindow()
        right_scroller.set_child(self.detail)
        root2.set_end_child(right_scroller)

        root.set_position(230)
        root2.set_position(430)

        self._rebuild_extra()

    # ----- list factories -----
    def _type_setup(self, factory, list_item):
        list_item.set_child(Gtk.Label(xalign=0))

    def _type_bind(self, factory, list_item):
        lbl = list_item.get_child()
        obj = list_item.get_item()
        lbl.set_label(obj.get_string())

    def _item_setup(self, factory, list_item):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(xalign=0)
        title.add_css_class("title-3")
        sub = Gtk.Label(xalign=0)
        sub.add_css_class("dim-label")
        box.append(title)
        box.append(sub)
        list_item.set_child(box)

    def _item_bind(self, factory, list_item):
        box = list_item.get_child()
        title = box.get_first_child()
        sub = title.get_next_sibling()
        obj = list_item.get_item()
        s = obj.get_string()
        parts = s.split("|", 3)
        name = parts[1]
        version = parts[2]
        updated = parts[3]
        title.set_label(name)
        sub.set_label(f"v{version} • updated {updated}")

    # ----- events -----
    def _on_type_selected(self, selection, _pspec):
        idx = selection.get_selected()
        if idx < 0:
            return
        self.current_type = ITEM_TYPES[idx][0]
        self.lbl_mid.set_label(ITEM_TYPES[idx][1])
        self.current_uuid = None
        self._clear_form()
        self._rebuild_extra()
        self._refresh_list()

    def _on_search_changed(self, _entry):
        self._refresh_list()

    def _on_item_selected(self, selection, _pspec):
        idx = selection.get_selected()
        if idx < 0:
            return
        obj = self.item_store.get_item(idx)
        item_uuid = obj.get_string().split("|", 3)[0]
        self.current_uuid = item_uuid
        self._load_item(item_uuid)

    def _on_new(self, _btn):
        self.current_uuid = None
        self._clear_form()
        self._rebuild_extra()
        prefix = {
            "DATA_ELEMENT": "de",
            "DATA_ELEMENT_CONCEPT": "dec",
            "VALUE_DOMAIN": "vd",
            "CONCEPTUAL_DOMAIN": "cd",
            "OBJECT_CLASS": "oc",
            "PROPERTY": "prop",
            "REPRESENTATION_CLASS": "rc",
            "CLASSIFICATION_SCHEME": "cs",
            "CLASSIFICATION_ITEM": "ci",
        }.get(self.current_type, "it")
        self.f_uuid.set_text(new_uuid(prefix))

    def _on_save(self, _btn):
        self.err.set_label("")
        try:
            self._save_current()
            self.conn.commit()
            self._refresh_list()
            if self.current_uuid:
                self._load_item(self.current_uuid)
        except Exception as e:
            self.conn.rollback()
            self.err.set_label(str(e))

    def _on_delete(self, _btn):
        self.err.set_label("")
        if not self.current_uuid:
            self.err.set_label("Kein Item ausgewählt.")
            return
        try:
            self.repo.delete_item(self.current_uuid)
            self.conn.commit()
            self.current_uuid = None
            self._clear_form()
            self._refresh_list()
        except Exception as e:
            self.conn.rollback()
            self.err.set_label(str(e))

    # ----- designations -----
    def _on_des_add(self, _btn):
        if not self._ensure_selected():
            return
        # add a blank row widget that will be persisted on Save (we store temp ids)
        row = _DesignationRow(self, des_uuid=new_uuid("des"), language="de", des_type="synonym", text="", is_pref=False)
        self.des_box.append(row.widget)

    def _on_des_delete(self, _btn):
        if not self._ensure_selected():
            return
        selected = getattr(self, "_selected_des_row", None)
        if not selected:
            self.err.set_label("Keine Designation ausgewählt (klicke in eine Zeile).")
            return
        des_uuid = selected.des_uuid
        try:
            self.repo.delete_designation(des_uuid)
            self.conn.commit()
            self._load_designations(self.current_uuid)
        except Exception as e:
            self.conn.rollback()
            self.err.set_label(str(e))

    # ----- classification assignments -----
    def _on_ic_add(self, _btn):
        if not self._ensure_selected():
            return
        if not self.ic_add_dd:
            self.err.set_label("Keine Classification Items vorhanden.")
            return
        ci_uuid = self.ic_add_dd.get_selected_uuid()
        if not ci_uuid:
            self.err.set_label("Bitte ein Classification Item auswählen.")
            return
        steward = self.f_steward.get_text().strip() or None
        self.repo.add_item_classification(self.current_uuid, ci_uuid, steward)
        self.conn.commit()
        self._load_classifications(self.current_uuid)

    def _on_ic_delete(self, _btn):
        if not self._ensure_selected():
            return
        selected = getattr(self, "_selected_ic_row", None)
        if not selected:
            self.err.set_label("Keine Zuordnung ausgewählt (klicke in eine Zeile).")
            return
        ic_uuid = selected.ic_uuid
        self.repo.delete_item_classification(ic_uuid)
        self.conn.commit()
        self._load_classifications(self.current_uuid)

    def _ensure_selected(self) -> bool:
        if not self.current_uuid:
            self.err.set_label("Bitte zuerst ein Item auswählen oder speichern.")
            return False
        return True

    # ----- data -----
    def _refresh_list(self):
        q = self.search.get_text().strip()
        rows = self.repo.list_items(self.current_type, q if q else None)
        self.item_store.remove_all()
        for r in rows:
            s = f"{r['uuid']}|{r['preferred_name']}|{r['version']}|{r['updated_at']}"
            self.item_store.append(Gtk.StringObject.new(s))

    def _clear_form(self):
        self.f_uuid.set_text("")
        self.f_name.set_text("")
        self._set_textview(self.f_def, "")
        self.f_reg_status.set_selected(0)
        self.f_admin_status.set_selected(0)
        self.f_steward.set_text("")
        self.footer.set_label("")
        self.err.set_label("")
        for c in list(self.extra):
            self.extra.remove(c)
        for c in list(self.des_box):
            self.des_box.remove(c)
        for c in list(self.ic_box):
            self.ic_box.remove(c)
        self.ic_add_dd = None

    def _load_item(self, uuid: str):
        item = self.repo.get_item(uuid)
        if not item:
            self.err.set_label("Item nicht gefunden.")
            return
        self.f_uuid.set_text(item["uuid"])
        self.f_name.set_text(item["preferred_name"])
        self._set_textview(self.f_def, item["definition"])
        self._select_in_dropdown(self.f_reg_status, item["registration_status"])
        self._select_in_dropdown(self.f_admin_status, item["administrative_status"])
        self.f_steward.set_text(item["steward"] or "")
        self.footer.set_label(f"Type: {item['item_type']} • Version: {item['version']} • Created: {item['created_at']} • Updated: {item['updated_at']}")
        self._rebuild_extra(load_uuid=uuid)
        self._load_designations(uuid)
        self._load_classifications(uuid)

    def _save_current(self):
        uuid = self.f_uuid.get_text().strip()
        name = self.f_name.get_text().strip()
        definition = self._get_textview(self.f_def).strip()
        if not uuid:
            raise ValueError("UUID fehlt (Neu klicken).")
        if not name:
            raise ValueError("Preferred Name ist Pflicht.")
        if not definition:
            raise ValueError("Definition ist Pflicht.")

        reg_status = self._dropdown_value(self.f_reg_status)
        admin_status = self._dropdown_value(self.f_admin_status)
        steward = self.f_steward.get_text().strip() or None

        existing = self.repo.get_item(uuid)
        if not existing:
            item = RegistrableItem(
                uuid=uuid,
                item_type=self.current_type,
                preferred_name=name,
                definition=definition,
                context_uuid="ctx-default",
                registration_authority_uuid="ra-local",
                registration_status=reg_status,
                administrative_status=admin_status,
                steward=steward,
                submitting_organization=None,
                version=1,
            )
            self.repo.create_item(item)
            self._save_entity_specific(uuid, is_new=True)
            self.current_uuid = uuid
        else:
            self.repo.update_item(uuid, {
                "preferred_name": name,
                "definition": definition,
                "registration_status": reg_status,
                "administrative_status": admin_status,
                "steward": steward,
            }, change_note="GUI update", changed_by=steward)
            self._save_entity_specific(uuid, is_new=False)
            self.current_uuid = uuid

        # Persist designations from UI
        self._persist_designations(uuid)

    # ----- entity specific -----
    def _rebuild_extra(self, load_uuid: str | None = None):
        for c in list(self.extra):
            self.extra.remove(c)

        if self.current_type == "VALUE_DOMAIN":
            self._build_value_domain(load_uuid)
        elif self.current_type == "DATA_ELEMENT_CONCEPT":
            self._build_dec(load_uuid)
        elif self.current_type == "DATA_ELEMENT":
            self._build_data_element(load_uuid)
        elif self.current_type == "CONCEPTUAL_DOMAIN":
            self._build_conceptual_domain(load_uuid)
        elif self.current_type == "CLASSIFICATION_SCHEME":
            self._build_classification_scheme(load_uuid)
        elif self.current_type == "CLASSIFICATION_ITEM":
            self._build_classification_item(load_uuid)
        else:
            self.extra.append(Gtk.Label(label="Keine zusätzlichen Felder für diesen Typ.", xalign=0))

    def _build_value_domain(self, load_uuid: str | None):
        self.extra.append(Gtk.Label(label="Value Domain Felder", xalign=0))
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        self.extra.append(grid)

        self.vd_datatype = Gtk.DropDown.new_from_strings(["string","integer","decimal","date","datetime","boolean","code"])
        self.vd_unit = Gtk.Entry()
        self.vd_maxlen = Gtk.SpinButton.new_with_range(0, 100000, 1)
        self.vd_maxlen.set_numeric(True)
        self.vd_format = Gtk.Entry()

        cd_opts = self.repo.fetch_refs("CONCEPTUAL_DOMAIN")
        self.vd_cd = _RefDropDown(cd_opts, allow_none=True)

        rc_opts = self.repo.fetch_refs("REPRESENTATION_CLASS")
        self.vd_rc = _RefDropDown(rc_opts, allow_none=True)

        def add(r, label, w):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, r, 1, 1)
            grid.attach(w, 1, r, 1, 1)

        add(0, "Datatype", self.vd_datatype)
        add(1, "Unit of measure", self.vd_unit)
        add(2, "Max length", self.vd_maxlen)
        add(3, "Format", self.vd_format)
        add(4, "Conceptual Domain", self.vd_cd.widget)
        add(5, "Representation Class", self.vd_rc.widget)

        # Permissible values
        self.extra.append(Gtk.Separator())
        self.extra.append(Gtk.Label(label="Permissible Values (enumerated)", xalign=0))
        self.pv_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.extra.append(self.pv_box)
        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.btn_pv_add = Gtk.Button(label="Permissible Value hinzufügen")
        self.btn_pv_add.connect("clicked", self._on_pv_add)
        self.btn_pv_del = Gtk.Button(label="Ausgewählten PV löschen")
        self.btn_pv_del.connect("clicked", self._on_pv_delete)
        btns.append(self.btn_pv_add)
        btns.append(self.btn_pv_del)
        self.extra.append(btns)

        if load_uuid:
            row = self.repo.get_value_domain(load_uuid)
            if row:
                self._select_in_dropdown(self.vd_datatype, row["datatype"])
                self.vd_unit.set_text(row["unit_of_measure"] or "")
                self.vd_maxlen.set_value(row["max_length"] or 0)
                self.vd_format.set_text(row["format"] or "")
                self.vd_cd.set_selected_uuid(row["conceptual_domain_uuid"])
                self.vd_rc.set_selected_uuid(row["representation_class_uuid"])
            self._load_pvs(load_uuid)

    def _on_pv_add(self, _btn):
        if not self._ensure_selected():
            return
        row = _PVRow(self, pv_uuid=new_uuid("pv"), code="", meaning="", sort_order=None)
        self.pv_box.append(row.widget)

    def _on_pv_delete(self, _btn):
        if not self._ensure_selected():
            return
        selected = getattr(self, "_selected_pv_row", None)
        if not selected:
            self.err.set_label("Keine PV ausgewählt (klicke in eine Zeile).")
            return
        self.repo.delete_permissible_value(selected.pv_uuid)
        self.conn.commit()
        self._load_pvs(self.current_uuid)

    def _load_pvs(self, vd_uuid: str):
        for c in list(self.pv_box):
            self.pv_box.remove(c)
        for r in self.repo.list_permissible_values(vd_uuid):
            row = _PVRow(self, pv_uuid=r["uuid"], code=r["code"], meaning=r["meaning"], sort_order=r["sort_order"])
            self.pv_box.append(row.widget)

    def _persist_pvs(self, vd_uuid: str):
        # iterate children, upsert if has code+meaning
        for child in list(self.pv_box):
            row = child._row_obj  # type: ignore
            code = row.code.get_text().strip()
            meaning = row.meaning.get_text().strip()
            if not code and not meaning:
                continue
            if not code or not meaning:
                raise ValueError("Permissible Value: Code und Meaning sind Pflicht (oder Zeile leer lassen).")
            so = row.sort.get_text().strip()
            sort_order = int(so) if so else None
            self.repo.upsert_permissible_value(row.pv_uuid, vd_uuid, code, meaning, sort_order)

    def _build_dec(self, load_uuid: str | None):
        self.extra.append(Gtk.Label(label="Data Element Concept Felder", xalign=0))
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        self.extra.append(grid)

        oc_opts = self.repo.fetch_refs("OBJECT_CLASS")
        prop_opts = self.repo.fetch_refs("PROPERTY")
        cd_opts = self.repo.fetch_refs("CONCEPTUAL_DOMAIN")

        self.dec_oc = _RefDropDown(oc_opts, allow_none=False)
        self.dec_prop = _RefDropDown(prop_opts, allow_none=False)
        self.dec_cd = _RefDropDown(cd_opts, allow_none=True)

        def add(r, label, w):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, r, 1, 1)
            grid.attach(w, 1, r, 1, 1)

        add(0, "Object Class*", self.dec_oc.widget)
        add(1, "Property*", self.dec_prop.widget)
        add(2, "Conceptual Domain", self.dec_cd.widget)

        if load_uuid:
            row = self.repo.get_data_element_concept(load_uuid)
            if row:
                self.dec_oc.set_selected_uuid(row["object_class_uuid"])
                self.dec_prop.set_selected_uuid(row["property_uuid"])
                self.dec_cd.set_selected_uuid(row["conceptual_domain_uuid"])

    def _build_data_element(self, load_uuid: str | None):
        self.extra.append(Gtk.Label(label="Data Element Felder", xalign=0))
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        self.extra.append(grid)

        dec_opts = self.repo.fetch_refs("DATA_ELEMENT_CONCEPT")
        vd_opts = self.repo.fetch_refs("VALUE_DOMAIN")

        self.de_dec = _RefDropDown(dec_opts, allow_none=False)
        self.de_vd = _RefDropDown(vd_opts, allow_none=False)

        grid.attach(Gtk.Label(label="Data Element Concept*", xalign=0), 0, 0, 1, 1)
        grid.attach(self.de_dec.widget, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Value Domain*", xalign=0), 0, 1, 1, 1)
        grid.attach(self.de_vd.widget, 1, 1, 1, 1)

        if load_uuid:
            row = self.repo.get_data_element(load_uuid)
            if row:
                self.de_dec.set_selected_uuid(row["data_element_concept_uuid"])
                self.de_vd.set_selected_uuid(row["value_domain_uuid"])

    def _build_conceptual_domain(self, load_uuid: str | None):
        self.extra.append(Gtk.Label(label="Conceptual Domain Felder", xalign=0))
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        self.extra.append(grid)

        self.cd_desc = Gtk.Entry()
        grid.attach(Gtk.Label(label="Description", xalign=0), 0, 0, 1, 1)
        grid.attach(self.cd_desc, 1, 0, 1, 1)

        if load_uuid:
            row = self.conn.execute("SELECT description FROM conceptual_domain WHERE uuid=?", (load_uuid,)).fetchone()
            if row:
                self.cd_desc.set_text(row["description"] or "")

    def _build_classification_scheme(self, load_uuid: str | None):
        self.extra.append(Gtk.Label(label="Classification Scheme Felder", xalign=0))
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        self.extra.append(grid)
        self.cs_uri = Gtk.Entry()
        grid.attach(Gtk.Label(label="Scheme URI", xalign=0), 0, 0, 1, 1)
        grid.attach(self.cs_uri, 1, 0, 1, 1)
        if load_uuid:
            row = self.repo.get_classification_scheme(load_uuid)
            if row:
                self.cs_uri.set_text(row["scheme_uri"] or "")

    def _build_classification_item(self, load_uuid: str | None):
        self.extra.append(Gtk.Label(label="Classification Item Felder", xalign=0))
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        self.extra.append(grid)

        scheme_opts = self.repo.fetch_refs("CLASSIFICATION_SCHEME")
        self.ci_scheme = _RefDropDown(scheme_opts, allow_none=False)

        # parent selection: allow selecting any classification item
        parent_opts = self.repo.fetch_refs("CLASSIFICATION_ITEM")
        self.ci_parent = _RefDropDown(parent_opts, allow_none=True)

        self.ci_code = Gtk.Entry()

        grid.attach(Gtk.Label(label="Scheme*", xalign=0), 0, 0, 1, 1)
        grid.attach(self.ci_scheme.widget, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Parent", xalign=0), 0, 1, 1, 1)
        grid.attach(self.ci_parent.widget, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label="Item code", xalign=0), 0, 2, 1, 1)
        grid.attach(self.ci_code, 1, 2, 1, 1)

        if load_uuid:
            row = self.repo.get_classification_item(load_uuid)
            if row:
                self.ci_scheme.set_selected_uuid(row["scheme_uuid"])
                self.ci_parent.set_selected_uuid(row["parent_uuid"])
                self.ci_code.set_text(row["item_code"] or "")

    def _save_entity_specific(self, uuid: str, is_new: bool):
        t = self.current_type
        if t == "OBJECT_CLASS":
            self.repo.ensure_row("object_class", uuid)
        elif t == "PROPERTY":
            self.repo.ensure_row("property", uuid)
        elif t == "REPRESENTATION_CLASS":
            self.repo.ensure_row("representation_class", uuid)
        elif t == "CONCEPTUAL_DOMAIN":
            self.repo.ensure_row("conceptual_domain", uuid)
            desc = getattr(self, "cd_desc", None)
            if desc:
                self.conn.execute("UPDATE conceptual_domain SET description=? WHERE uuid=?", (desc.get_text().strip() or None, uuid))
        elif t == "VALUE_DOMAIN":
            dt = self._dropdown_value(self.vd_datatype)
            unit = self.vd_unit.get_text().strip() or None
            maxlen = int(self.vd_maxlen.get_value()) or None
            fmt = self.vd_format.get_text().strip() or None
            cd = self.vd_cd.get_selected_uuid()
            rc = self.vd_rc.get_selected_uuid()
            self.repo.upsert_value_domain(uuid, dt, unit, maxlen, fmt, cd, rc)
            # pvs
            self._persist_pvs(uuid)
        elif t == "DATA_ELEMENT_CONCEPT":
            oc = self.dec_oc.get_selected_uuid()
            prop = self.dec_prop.get_selected_uuid()
            cd = self.dec_cd.get_selected_uuid()
            if not oc or not prop:
                raise ValueError("Object Class und Property sind Pflicht.")
            self.repo.upsert_data_element_concept(uuid, oc, prop, cd)
        elif t == "DATA_ELEMENT":
            dec = self.de_dec.get_selected_uuid()
            vd = self.de_vd.get_selected_uuid()
            if not dec or not vd:
                raise ValueError("DEC und Value Domain sind Pflicht.")
            self.repo.upsert_data_element(uuid, dec, vd)
        elif t == "CLASSIFICATION_SCHEME":
            self.repo.ensure_row("classification_scheme", uuid)
            uri = getattr(self, "cs_uri", None)
            self.repo.upsert_classification_scheme(uuid, uri.get_text().strip() or None if uri else None)
        elif t == "CLASSIFICATION_ITEM":
            self.repo.ensure_row("classification_item", uuid)  # table has more cols, but ignore insert errors? it requires scheme_uuid not null.
            # we'll upsert properly:
            scheme = self.ci_scheme.get_selected_uuid()
            if not scheme:
                raise ValueError("Scheme ist Pflicht.")
            parent = self.ci_parent.get_selected_uuid()
            code = self.ci_code.get_text().strip() or None
            self.repo.upsert_classification_item(uuid, scheme, parent, code)

    # ----- Designations UI load/persist -----
    def _load_designations(self, item_uuid: str | None):
        for c in list(self.des_box):
            self.des_box.remove(c)
        if not item_uuid:
            return
        for r in self.repo.list_designations(item_uuid):
            row = _DesignationRow(self, des_uuid=r["uuid"], language=r["language_tag"], des_type=r["designation_type"],
                                 text=r["designation"], is_pref=bool(r["is_preferred"]))
            self.des_box.append(row.widget)

    def _persist_designations(self, item_uuid: str):
        # upsert all rows in UI (ignore fully empty)
        for child in list(self.des_box):
            row = child._row_obj  # type: ignore
            lang = row.lang.get_text().strip() or "und"
            des_type = row.typ.get_selected_item().get_string() if row.typ.get_selected_item() else "synonym"
            text = row.text.get_text().strip()
            is_pref = 1 if row.pref.get_active() else 0
            if not text:
                continue
            self.repo.upsert_designation(row.des_uuid, item_uuid, "ctx-default", lang, des_type, text, is_pref)

    # ----- Classification assignments UI -----
    def _load_classifications(self, item_uuid: str | None):
        for c in list(self.ic_box):
            self.ic_box.remove(c)
        if not item_uuid:
            return

        # build add dropdown with all classification items
        ci_opts = self.repo.fetch_refs("CLASSIFICATION_ITEM")
        self.ic_add_dd = _RefDropDown(ci_opts, allow_none=True)
        # place dropdown at top
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        top.append(Gtk.Label(label="Classification Item wählen:", xalign=0))
        top.append(self.ic_add_dd.widget)
        self.ic_box.append(top)

        for r in self.repo.list_item_classifications(item_uuid):
            row = _ICRow(self, ic_uuid=r["uuid"], scheme=r["scheme_name"], item=r["classification_item_name"])
            self.ic_box.append(row.widget)

    # ----- small widget helpers -----
    def _dropdown_value(self, dd: Gtk.DropDown) -> str:
        obj = dd.get_selected_item()
        return obj.get_string() if obj else ""

    def _select_in_dropdown(self, dd: Gtk.DropDown, value: str):
        model = dd.get_model()
        for i in range(model.get_n_items()):
            if model.get_item(i).get_string() == value:
                dd.set_selected(i)
                return

    def _get_textview(self, tv: Gtk.TextView) -> str:
        buf = tv.get_buffer()
        start, end = buf.get_bounds()
        return buf.get_text(start, end, True)

    def _set_textview(self, tv: Gtk.TextView, text: str):
        tv.get_buffer().set_text(text)

# ----- Import/Export dialogs (GTK4 FileDialog) -----
    def export_json_dialog(self):
        dlg = Gtk.FileDialog(title="Export JSON", initial_name="mdr-export.json")
        dlg.save(self, None, self._on_export_json_done)

    def _on_export_json_done(self, dlg, res):
        try:
            file = dlg.save_finish(res)
            path = file.get_path()
            self._export_json(path)
        except Exception as e:
            self.err.set_label(str(e))

    def import_json_dialog(self):
        dlg = Gtk.FileDialog(title="Import JSON")
        filt = Gtk.FileFilter()
        filt.set_name("JSON files")
        filt.add_pattern("*.json")
        dlg.set_default_filter(filt)
        dlg.open(self, None, self._on_import_json_done)

    def _on_import_json_done(self, dlg, res):
        try:
            file = dlg.open_finish(res)
            path = file.get_path()
            self._import_json(path)
            self._refresh_list()
            if self.current_uuid:
                self._load_item(self.current_uuid)
        except Exception as e:
            self.err.set_label(str(e))

    def export_csv_dialog(self):
        dlg = Gtk.FileDialog(title="Export CSV", initial_name="mdr-export.csv")
        dlg.save(self, None, self._on_export_csv_done)

    def _on_export_csv_done(self, dlg, res):
        try:
            file = dlg.save_finish(res)
            path = file.get_path()
            self._export_csv(path)
        except Exception as e:
            self.err.set_label(str(e))

    def export_skos_dialog(self):
        dlg = Gtk.FileDialog(title="Export SKOS (Turtle)", initial_name="mdr-export.ttl")
        dlg.save(self, None, self._on_export_skos_done)

    def _on_export_skos_done(self, dlg, res):
        try:
            file = dlg.save_finish(res)
            path = file.get_path()
            self._export_skos(path, base="urn:example:mdr:")
        except Exception as e:
            self.err.set_label(str(e))

    def _export_json(self, out_path: str):
        data = {}
        for table in [
            "context",
            "registration_authority",
            "registrable_item",
            "conceptual_domain",
            "representation_class",
            "object_class",
            "property",
            "data_element_concept",
            "value_domain",
            "data_element",
            "designation",
            "permissible_value",
            "classification_scheme",
            "classification_item",
            "item_classification",
            "item_version",
        ]:
            rows = self.conn.execute(f"SELECT * FROM {table}").fetchall()
            data[table] = [dict(r) for r in rows]
        Path(out_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.err.set_label(f"OK: Export JSON → {out_path}")

    def _import_json(self, in_path: str):
        payload = json.loads(Path(in_path).read_text(encoding="utf-8"))

        def upsert(table: str, row: dict):
            cols = list(row.keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_list = ", ".join(cols)
            update_cols = [c for c in cols if c != "uuid"]
            update_stmt = ", ".join([f"{c}=excluded.{c}" for c in update_cols]) if update_cols else ""
            if update_stmt:
                sql = f"INSERT INTO {table}({col_list}) VALUES({placeholders}) ON CONFLICT(uuid) DO UPDATE SET {update_stmt}"
            else:
                sql = f"INSERT INTO {table}({col_list}) VALUES({placeholders}) ON CONFLICT(uuid) DO NOTHING"
            self.conn.execute(sql, [row[c] for c in cols])

        self.conn.execute("BEGIN;")
        try:
            for table in ["context","registration_authority"]:
                for row in payload.get(table, []):
                    upsert(table, row)

            for row in payload.get("registrable_item", []):
                upsert("registrable_item", row)

            for table in [
                "conceptual_domain","representation_class","object_class","property",
                "classification_scheme","classification_item",
                "data_element_concept","value_domain","data_element",
            ]:
                for row in payload.get(table, []):
                    upsert(table, row)

            for table in ["designation","permissible_value","item_classification","item_version"]:
                for row in payload.get(table, []):
                    upsert(table, row)

            self.conn.commit()
            self.err.set_label(f"OK: Import JSON ← {in_path}")
        except Exception:
            self.conn.rollback()
            raise

    def _export_csv(self, out_path: str):
        fields = [
            "uuid","item_type","preferred_name","definition",
            "context_uuid","registration_authority_uuid",
            "registration_status","administrative_status",
            "steward","submitting_organization","version",
            "created_at","updated_at",
            "vd_datatype","vd_unit_of_measure","vd_max_length","vd_format","vd_conceptual_domain_uuid","vd_representation_class_uuid",
            "dec_object_class_uuid","dec_property_uuid","dec_conceptual_domain_uuid",
            "de_data_element_concept_uuid","de_value_domain_uuid",
            "cs_scheme_uri",
            "ci_scheme_uuid","ci_parent_uuid","ci_item_code",
            "cd_description",
        ]
        rows = self.conn.execute(
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
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            wri = csv.DictWriter(f, fieldnames=fields)
            wri.writeheader()
            for r in rows:
                d = {k: (r[k] if k in r.keys() else None) for k in fields}
                wri.writerow(d)
        self.err.set_label(f"OK: Export CSV → {out_path}")

    def _export_skos(self, out_path: str, base: str):
        def esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        def iri(u: str) -> str:
            return f"{base}{u}"

        lines = []
        lines.append("@prefix skos: <http://www.w3.org/2004/02/skos/core#> .")
        lines.append("@prefix dcterms: <http://purl.org/dc/terms/> .")
        lines.append("")
        scheme_items = "urn:mdr:items"
        lines.append(f"<{scheme_items}> a skos:ConceptScheme ; skos:prefLabel \"MDR Items\"@en .")
        lines.append("")

        schemes = self.conn.execute(
            """
            SELECT ri.uuid, ri.preferred_name, ri.definition, cs.scheme_uri
            FROM classification_scheme cs
            JOIN registrable_item ri ON ri.uuid = cs.uuid
            """
        ).fetchall()
        for s in schemes:
            s_iri = iri(s["uuid"])
            lines.append(f"<{s_iri}> a skos:ConceptScheme ;")
            lines.append(f"  skos:prefLabel \"{esc(s['preferred_name'])}\"@en ;")
            lines.append(f"  skos:definition \"{esc(s['definition'])}\"@en ;")
            if s["scheme_uri"]:
                lines.append(f"  dcterms:identifier \"{esc(s['scheme_uri'])}\" ;")
            lines[-1] = lines[-1].rstrip(" ;") + " ."
            lines.append("")

        cis = self.conn.execute(
            """
            SELECT ri.uuid, ri.preferred_name, ri.definition, ci.scheme_uuid, ci.parent_uuid, ci.item_code
            FROM classification_item ci
            JOIN registrable_item ri ON ri.uuid = ci.uuid
            """
        ).fetchall()
        for c in cis:
            c_iri = iri(c["uuid"])
            lines.append(f"<{c_iri}> a skos:Concept ;")
            lines.append(f"  skos:inScheme <{iri(c['scheme_uuid'])}> ;")
            lines.append(f"  skos:prefLabel \"{esc(c['preferred_name'])}\"@en ;")
            lines.append(f"  skos:definition \"{esc(c['definition'])}\"@en ;")
            if c["item_code"]:
                lines.append(f"  dcterms:identifier \"{esc(c['item_code'])}\" ;")
            if c["parent_uuid"]:
                lines.append(f"  skos:broader <{iri(c['parent_uuid'])}> ;")
            lines[-1] = lines[-1].rstrip(" ;") + " ."
            lines.append("")

        items = self.conn.execute("SELECT uuid, item_type, preferred_name, definition FROM registrable_item").fetchall()
        for it in items:
            it_iri = iri(it["uuid"])
            lines.append(f"<{it_iri}> a skos:Concept ;")
            lines.append(f"  skos:inScheme <{scheme_items}> ;")
            lines.append(f"  skos:prefLabel \"{esc(it['preferred_name'])}\"@en ;")
            lines.append(f"  skos:definition \"{esc(it['definition'])}\"@en ;")
            lines.append(f"  dcterms:type \"{esc(it['item_type'])}\" ;")
            lines[-1] = lines[-1].rstrip(" ;") + " ."
            lines.append("")

        des = self.conn.execute("SELECT item_uuid, language_tag, designation, designation_type, is_preferred FROM designation").fetchall()
        for d in des:
            subj = f"<{iri(d['item_uuid'])}>"
            lang = d["language_tag"] or "und"
            text = esc(d["designation"])
            pred = "skos:prefLabel" if (d["designation_type"] == "preferred" or d["is_preferred"] == 1) else "skos:altLabel"
            lines.append(f"{subj} {pred} \"{text}\"@{lang} .")
        lines.append("")

        ics = self.conn.execute("SELECT item_uuid, classification_item_uuid FROM item_classification").fetchall()
        for ic in ics:
            lines.append(f"<{iri(ic['item_uuid'])}> dcterms:subject <{iri(ic['classification_item_uuid'])}> .")

        Path(out_path).write_text("\\n".join(lines), encoding="utf-8")
        self.err.set_label(f"OK: Export SKOS → {out_path}")

# ----------------------------
# Logging
# ----------------------------
    # ----------------------------
    # Logging
    # ----------------------------
    def _log(self, msg: str) -> None:
        line = msg.strip()
        if not line:
            return
        ts = self.conn.execute("SELECT strftime('%Y-%m-%d %H:%M:%S','now')").fetchone()[0]
        self.log_lines.append(f"[{ts}] {line}")
        if len(self.log_lines) > 5000:
            self.log_lines = self.log_lines[-2000:]
        if hasattr(self, "log_buffer"):
            self.log_buffer.set_text("\n".join(self.log_lines))

    # ----------------------------
    # DB open/new
    # ----------------------------
    def _reopen_db(self, new_path: str) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
        self.conn = connect(new_path)
        self._ensure_schema()
        self.repo = Repo(self.conn)
        self.db_path = new_path
        self._log(f"DB opened: {new_path}")
        self._refresh_list()
        self._refresh_fhir_views()

    def open_db_dialog(self) -> None:
        dlg = Gtk.FileChooserNative.new("Open SQLite DB", self, Gtk.FileChooserAction.OPEN, "Open", "Cancel")
        filt = Gtk.FileFilter()
        filt.set_name("SQLite DB")
        filt.add_pattern("*.sqlite")
        filt.add_pattern("*.db")
        dlg.add_filter(filt)

        def on_response(d, resp):
            if resp == Gtk.ResponseType.ACCEPT:
                f = d.get_file()
                if f:
                    self._reopen_db(f.get_path())
            d.destroy()

        dlg.connect("response", on_response)
        dlg.show()

    def new_db_dialog(self) -> None:
        dlg = Gtk.FileChooserNative.new("Create SQLite DB", self, Gtk.FileChooserAction.SAVE, "Create", "Cancel")
        dlg.set_current_name("mdr.sqlite")

        def on_response(d, resp):
            if resp == Gtk.ResponseType.ACCEPT:
                f = d.get_file()
                if f:
                    self._reopen_db(f.get_path())
            d.destroy()

        dlg.connect("response", on_response)
        dlg.show()

    # ----------------------------
    # FHIR page + views
    # ----------------------------
    def _simple_setup(self, factory, list_item):
        lbl = Gtk.Label(xalign=0)
        lbl.set_wrap(True)
        lbl.set_selectable(True)
        list_item.set_child(lbl)

    def _simple_bind(self, factory, list_item):
        obj = list_item.get_item()
        lbl = list_item.get_child()
        if obj and lbl:
            lbl.set_text(obj.get_string())

    def _build_fhir_page(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.append(Gtk.Label(label="FHIR", xalign=0))

        btn_refresh = Gtk.Button(label="Refresh")
        btn_refresh.connect("clicked", lambda *_: self._refresh_fhir_views())
        bar.append(btn_refresh)

        btn_imp_bundle = Gtk.Button(label="Import Bundle (JSON)…")
        btn_imp_bundle.connect("clicked", lambda *_: self._guarded('FHIR Import Bundle', self.import_fhir_bundle_dialog))
        bar.append(btn_imp_bundle)

        btn_imp_pkg = Gtk.Button(label="Import Package (.tgz)…")
        btn_imp_pkg.connect("clicked", lambda *_: self._guarded('FHIR Import Package', self.import_fhir_package_dialog))
        bar.append(btn_imp_pkg)

        btn_imp_dir = Gtk.Button(label="Import Package (dir)…")
        btn_imp_dir.connect("clicked", lambda *_: self._guarded('FHIR Import Package Dir', self.import_fhir_package_dir_dialog))
        bar.append(btn_imp_dir)

        btn_exp_json = Gtk.Button(label="Export Bundle JSON…")
        btn_exp_json.connect("clicked", lambda *_: self._guarded('FHIR Export Bundle JSON', self.export_fhir_bundle_json_dialog))
        bar.append(btn_exp_json)

        btn_exp_xml = Gtk.Button(label="Export Bundle XML…")
        btn_exp_xml.connect("clicked", lambda *_: self._guarded('FHIR Export Bundle XML', self.export_fhir_bundle_xml_dialog))
        bar.append(btn_exp_xml)

        self.btn_export_selected_json = Gtk.Button(label="Export Selected JSON…")
        self.btn_export_selected_json.connect("clicked", lambda *_: self._guarded('FHIR Export Selected JSON', self.export_fhir_selected_json_dialog))
        bar.append(self.btn_export_selected_json)

        self.btn_export_selected_xml = Gtk.Button(label="Export Selected XML…")
        self.btn_export_selected_xml.connect("clicked", lambda *_: self._guarded('FHIR Export Selected XML', self.export_fhir_selected_xml_dialog))
        bar.append(self.btn_export_selected_xml)

        outer.append(bar)

        # Filters (G3)
        frow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        frow.append(Gtk.Label(label="Type:", xalign=0))
        self.fhir_type_dd = Gtk.DropDown.new_from_strings(["All"])
        self.fhir_type_dd.connect("notify::selected", lambda *_: self._on_filter_changed())
        frow.append(self.fhir_type_dd)

        frow.append(Gtk.Label(label="Search:", xalign=0))
        self.fhir_search_entry = Gtk.SearchEntry()
        self.fhir_search_entry.set_placeholder_text("canonical_url or logical_id…")
        self.fhir_search_entry.connect("search-changed", lambda *_: self._on_filter_changed())
        frow.append(self.fhir_search_entry)

        self.fhir_conflicts_only = Gtk.CheckButton(label="conflicts only")
        self.fhir_conflicts_only.connect("toggled", lambda *_: self._on_filter_changed())
        frow.append(self.fhir_conflicts_only)

        frow.append(Gtk.Label(label="Limit:", xalign=0))
        self.fhir_limit_spin = Gtk.SpinButton.new_with_range(50, 5000, 50)
        self.fhir_limit_spin.set_value(500)
        self.fhir_limit_spin.connect("value-changed", lambda *_: self._on_filter_changed())
        frow.append(self.fhir_limit_spin)

        self.fhir_clear_btn = Gtk.Button(label="Clear filters")
        self.fhir_clear_btn.connect("clicked", lambda *_: self._clear_filters())
        frow.append(self.fhir_clear_btn)

        self.fhir_selected_lbl = Gtk.Label(label="Selected: 0", xalign=0)
        frow.append(self.fhir_selected_lbl)

        outer.append(frow)

        paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)

        outer.append(paned)

        # Left: stack + detail pane
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        paned.set_start_child(left)

        vpaned = Gtk.Paned.new(Gtk.Orientation.VERTICAL)
        vpaned.set_vexpand(True)
        left.append(vpaned)

        topbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vpaned.set_start_child(topbox)

        self.fhir_stack = Gtk.Stack()
        self.fhir_stack.set_vexpand(True)
        switcher = Gtk.StackSwitcher(stack=self.fhir_stack)
        topbox.append(switcher)
        topbox.append(self.fhir_stack)

        self._fhir_views = {}
        self._fhir_selections = {}

        for key, title in [
            ("curated", "Curated Resources"),
            ("conflicts", "Conflicts"),
            ("variants", "Variants"),
            ("runs", "Ingest Runs"),
        ]:
            store = Gio.ListStore.new(Gtk.StringObject)
            if key == "curated":
                sel = Gtk.MultiSelection.new(store)
            else:
                sel = Gtk.SingleSelection.new(store)
            self._fhir_selections[key] = sel
            factory = Gtk.SignalListItemFactory()
            factory.connect("setup", self._simple_setup)
            factory.connect("bind", self._simple_bind)
            view = Gtk.ListView.new(sel, factory)
            view.set_vexpand(True)
            if key == "curated":
                sel.connect("selection-changed", lambda s, _pos, _n, k=key: (self._on_fhir_select(k, s), self._update_selected_ui()))
            else:
                sel.connect("notify::selected", lambda s, _p, k=key: self._on_fhir_select(k, s))
            sc = Gtk.ScrolledWindow()
            sc.set_child(view)
            self.fhir_stack.add_titled(sc, key, title)
            self._fhir_views[key] = store

        self.fhir_detail_buffer = Gtk.TextBuffer()
        detail_tv = Gtk.TextView(buffer=self.fhir_detail_buffer)
        detail_tv.set_editable(False)
        detail_tv.set_cursor_visible(False)
        sc_detail = Gtk.ScrolledWindow()
        sc_detail.set_child(detail_tv)
        sc_detail.set_vexpand(True)
        vpaned.set_end_child(sc_detail)

        # Right: log
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        paned.set_end_child(right)
        right.append(Gtk.Label(label="Log", xalign=0))
        self.log_buffer = Gtk.TextBuffer()
        tv = Gtk.TextView(buffer=self.log_buffer)
        tv.set_editable(False)
        tv.set_cursor_visible(False)
        sc_log = Gtk.ScrolledWindow()
        sc_log.set_child(tv)
        sc_log.set_vexpand(True)
        right.append(sc_log)

        self._refresh_fhir_views()
        return outer

def _on_filter_changed(self) -> None:
    try:
        wanted = None
        model = self.fhir_type_dd.get_model() if hasattr(self, "fhir_type_dd") else None
        idx = int(self.fhir_type_dd.get_selected()) if hasattr(self, "fhir_type_dd") else 0
        if model and idx >= 0 and idx < model.get_n_items():
            obj = model.get_item(idx)
            if obj:
                s = obj.get_string()
                wanted = None if s == "All" else s
        self.curated_filter.resource_type = wanted

        t = self.fhir_search_entry.get_text() if hasattr(self, "fhir_search_entry") else ""
        self.curated_filter.text = t.strip() if t and t.strip() else None

        self.curated_filter.conflicts_only = bool(self.fhir_conflicts_only.get_active()) if hasattr(self, "fhir_conflicts_only") else False

        lim = int(self.fhir_limit_spin.get_value()) if hasattr(self, "fhir_limit_spin") else 500
        self.curated_filter.limit = lim

        self._refresh_fhir_views()
    except Exception as e:
        self._log(f"Filter update failed: {e}")

def _clear_filters(self) -> None:
    try:
        # Reset widgets
        if hasattr(self, "fhir_type_dd"):
            self.fhir_type_dd.set_selected(0)  # All
        if hasattr(self, "fhir_search_entry"):
            self.fhir_search_entry.set_text("")
        if hasattr(self, "fhir_conflicts_only"):
            self.fhir_conflicts_only.set_active(False)
        if hasattr(self, "fhir_limit_spin"):
            self.fhir_limit_spin.set_value(500)

        # Reset model
        self.curated_filter.resource_type = None
        self.curated_filter.text = None
        self.curated_filter.conflicts_only = False
        self.curated_filter.limit = 500

        self._refresh_fhir_views()
    except Exception as e:
        self._log(f"Clear filters failed: {e}")

def _update_selected_ui(self) -> None:
    try:
        idents = self._get_selected_curated_idents() if hasattr(self, "_get_selected_curated_idents") else []
        n = len(idents)
        if hasattr(self, "fhir_selected_lbl"):
            self.fhir_selected_lbl.set_text(f"Selected: {n}")
        # Update button labels if present
        if hasattr(self, "btn_export_selected_json"):
            self.btn_export_selected_json.set_label(f"Export Selected JSON… ({n})" if n else "Export Selected JSON…")
        if hasattr(self, "btn_export_selected_xml"):
            self.btn_export_selected_xml.set_label(f"Export Selected XML… ({n})" if n else "Export Selected XML…")
    except Exception:
        pass

    def _refresh_fhir_views(self) -> None:
        # Curated
        try:
            # Update type dropdown choices
            types = [r[0] for r in self.conn.execute(
                "SELECT DISTINCT resource_type FROM fhir_curated_resource ORDER BY resource_type"
            ).fetchall()]
            if hasattr(self, "fhir_type_dd"):
                items = ["All"] + [t for t in types if t]
                self.fhir_type_dd.set_model(Gtk.StringList.new(items))
                wanted = self.curated_filter.resource_type or "All"
                try:
                    self.fhir_type_dd.set_selected(items.index(wanted))
                except ValueError:
                    self.fhir_type_dd.set_selected(0)

            sql, params = build_curated_query(self.curated_filter)
            rows = self.conn.execute(sql, params).fetchall()
            self._fhir_views["curated"].remove_all()
            for r in rows:
                self._fhir_views["curated"].append(Gtk.StringObject.new(
                    f"{r[0]} | {r[1]} | v={r[2]} | conflict={r[3]} | {r[4]}"
                ))
        except Exception as e:
            self._log(f"FHIR curated view failed: {e}")

        # Conflicts
        try:
            rows = self.conn.execute(
                "SELECT resource_type, canonical_url, artifact_version, variant_count "
                "FROM v_fhir_artifact_conflicts ORDER BY variant_count DESC LIMIT 500"
            ).fetchall()
            self._fhir_views["conflicts"].remove_all()
            for r in rows:
                self._fhir_views["conflicts"].append(Gtk.StringObject.new(
                    f"{r[0]} | {r[1]} | v={r[2]} | variants={r[3]}"
                ))
        except Exception as e:
            self._log(f"FHIR conflicts view failed: {e}")

        # Variants
        try:
            rows = self.conn.execute(
                "SELECT c.resource_type, IFNULL(c.canonical_url, c.logical_id) as ident, v.resource_sha256, v.occurrences "
                "FROM fhir_curated_variant v JOIN fhir_curated_resource c ON c.curated_id=v.curated_id "
                "ORDER BY v.occurrences DESC LIMIT 500"
            ).fetchall()
            self._fhir_views["variants"].remove_all()
            for r in rows:
                self._fhir_views["variants"].append(Gtk.StringObject.new(
                    f"{r[0]} | {r[1]} | occ={r[3]} | sha={r[2][:12]}…"
                ))
        except Exception as e:
            self._log(f"FHIR variants view failed: {e}")

        # Runs
        try:
            rows = self.conn.execute(
                "SELECT run_id, started_ts, finished_ts, source_kind, source_name "
                "FROM fhir_ingest_run ORDER BY run_id DESC LIMIT 200"
            ).fetchall()
            self._fhir_views["runs"].remove_all()
            for r in rows:
                self._fhir_views["runs"].append(Gtk.StringObject.new(
                    f"run={r[0]} | {r[3]} | {r[4]} | {r[1]} -> {r[2] or ''}"
                ))
        except Exception as e:
            self._log(f"FHIR runs view failed: {e}")

    def _on_fhir_select(self, view_key: str, selection: Gtk.SingleSelection) -> None:
        try:
            if view_key == "curated" and isinstance(selection, Gtk.MultiSelection):
                obj = None
                model = selection.get_model()
                n = model.get_n_items() if model else 0
                for i in range(min(n, 5000)):
                    if selection.is_selected(i):
                        obj = model.get_item(i)
                        break
                if obj is None:
                    return
                line = obj.get_string()
            else:
                idx = selection.get_selected()
                if idx is None or idx < 0:
                    return
                obj = selection.get_selected_item()
                if obj is None:
                    return
                line = obj.get_string()

            if view_key == "curated":
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 2:
                    ident = parts[1]
                    info = get_curated_by_ident(self.conn, ident)
                    if not info:
                        self.fhir_detail_buffer.set_text("No curated info found.")
                        return
                    variants = get_variants_for_curated(self.conn, info.curated_id, limit=25)
                    raw = get_raw_json_by_sha(self.conn, info.current_sha256)
                    detail = []
                    detail.append(f"Curated: {info.resource_type}")
                    detail.append(f"Ident: {info.canonical_or_id}")
                    detail.append(f"Version: {info.artifact_version}")
                    detail.append(f"Current SHA: {info.current_sha256}")
                    detail.append(f"Conflict: {info.has_conflict}")
                    detail.append("")
                    detail.append("Variants (sha, occurrences):")
                    for sha, occ in variants:
                        detail.append(f"  - {sha}  occ={occ}")
                    detail.append("")
                    if raw is not None:
                        detail.append("Current resource_json (truncated):")
                        txt = json.dumps(raw, indent=2, ensure_ascii=False)
                        if len(txt) > 20000:
                            txt = txt[:20000] + "\n…(truncated)…"
                        detail.append(txt)
                    self.fhir_detail_buffer.set_text("\n".join(detail))
                    return

            self.fhir_detail_buffer.set_text(line)
        except Exception as e:
            self._log(f"Detail render failed: {e}")

    # ----------------------------
    # FHIR dialogs
    # ----------------------------
    def import_fhir_bundle_dialog(self) -> None:
        dlg = Gtk.FileChooserNative.new("Import FHIR Bundle (JSON)", self, Gtk.FileChooserAction.OPEN, "Import", "Cancel")
        filt = Gtk.FileFilter(); filt.set_name("JSON"); filt.add_pattern("*.json")
        dlg.add_filter(filt)

        def on_response(d, resp):
            if resp == Gtk.ResponseType.ACCEPT:
                f = d.get_file()
                if f:
                    path = f.get_path()
                    try:
                        obj = json.loads(Path(path).read_text(encoding="utf-8"))
                        res = import_fhir_bundle_json(self.conn, obj, source_name=f"file:{Path(path).name}")
                        self._log(res.message)
                        self._refresh_fhir_views()
                    except Exception as e:
                        self._log(f"FHIR bundle import failed: {e}")
            d.destroy()

        dlg.connect("response", on_response)
        dlg.show()

    def import_fhir_package_dialog(self) -> None:
        dlg = Gtk.FileChooserNative.new("Import FHIR Package (.tgz)", self, Gtk.FileChooserAction.OPEN, "Import", "Cancel")
        filt = Gtk.FileFilter(); filt.set_name("TGZ"); filt.add_pattern("*.tgz"); filt.add_pattern("*.tar.gz"); filt.add_pattern("*.gz")
        dlg.add_filter(filt)

        def on_response(d, resp):
            if resp == Gtk.ResponseType.ACCEPT:
                f = d.get_file()
                if f:
                    path = f.get_path()
                    try:
                        res = import_fhir_package(self.conn, path, source_name=f"file:{Path(path).name}")
                        self._log(res.message)
                        self._refresh_fhir_views()
                    except Exception as e:
                        self._log(f"FHIR package import failed: {e}")
            d.destroy()

        dlg.connect("response", on_response)
        dlg.show()

    def import_fhir_package_dir_dialog(self) -> None:
        dlg = Gtk.FileChooserNative.new("Import FHIR Package Directory", self, Gtk.FileChooserAction.SELECT_FOLDER, "Import", "Cancel")

        def on_response(d, resp):
            if resp == Gtk.ResponseType.ACCEPT:
                f = d.get_file()
                if f:
                    path = f.get_path()
                    try:
                        res = import_fhir_package(self.conn, path, source_name=f"dir:{Path(path).name}")
                        self._log(res.message)
                        self._refresh_fhir_views()
                    except Exception as e:
                        self._log(f"FHIR package dir import failed: {e}")
            d.destroy()

        dlg.connect("response", on_response)
        dlg.show()

    def export_fhir_bundle_json_dialog(self) -> None:
        dlg = Gtk.FileChooserNative.new("Export Curated Bundle (JSON)", self, Gtk.FileChooserAction.SAVE, "Export", "Cancel")
        dlg.set_current_name("curated.bundle.json")

        def on_response(d, resp):
            if resp == Gtk.ResponseType.ACCEPT:
                f = d.get_file()
                if f:
                    out = f.get_path()
                    try:
                        res = export_curated_bundle_json(self.conn, out, limit=2000)
                        self._log(res.message)
                    except Exception as e:
                        self._log(f"FHIR export JSON failed: {e}")
            d.destroy()

        dlg.connect("response", on_response)
        dlg.show()

    def export_fhir_bundle_xml_dialog(self) -> None:
        dialog = Gtk.Dialog(title="Export Curated Bundle (XML)", transient_for=self, modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Next…", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        row.append(Gtk.Label(label="Mode:", xalign=0))
        mode = Gtk.DropDown.new_from_strings(["best-effort","strict","strictish"])
        row.append(mode)
        box.append(row)

        def on_resp(d, resp):
            if resp == Gtk.ResponseType.OK:
                mode_str = ["best-effort","strict","strictish"][mode.get_selected()]
                d.destroy()
                save = Gtk.FileChooserNative.new("Save XML", self, Gtk.FileChooserAction.SAVE, "Export", "Cancel")
                save.set_current_name("curated.bundle.xml")

                def on_save(sd, sresp):
                    if sresp == Gtk.ResponseType.ACCEPT:
                        f = sd.get_file()
                        if f:
                            out = f.get_path()
                            try:
                                res = export_curated_bundle_xml(self.conn, out, limit=2000, mode=mode_str)
                                self._log(res.message)
                            except Exception as e:
                                self._log(f"FHIR export XML failed: {e}")
                    sd.destroy()

                save.connect("response", on_save)
                save.show()
            else:
                d.destroy()

        dialog.connect("response", on_resp)
        dialog.show()

def _get_selected_curated_idents(self) -> list[str]:
    try:
        sel = self._fhir_selections.get("curated")
        if isinstance(sel, Gtk.MultiSelection):
            model = sel.get_model()
            if not model:
                return []
            n = model.get_n_items()
            idents: list[str] = []
            for i in range(min(n, 5000)):
                if sel.is_selected(i):
                    obj = model.get_item(i)
                    if not obj:
                        continue
                    parts = [p.strip() for p in obj.get_string().split("|")]
                    if len(parts) >= 2:
                        idents.append(parts[1])
            return idents
    except Exception:
        return []
    one = self._get_selected_curated_ident()
    return [one] if one else []

def _get_selected_curated_ident(self) -> str | None:

        # Try to parse from detail view ("Ident: ...")
        try:
            txt = self.fhir_detail_buffer.get_text(
                self.fhir_detail_buffer.get_start_iter(),
                self.fhir_detail_buffer.get_end_iter(),
                True
            )
            for line in txt.splitlines():
                if line.startswith("Ident:"):
                    return line.split("Ident:", 1)[1].strip()
        except Exception:
            return None
        return None

def export_fhir_selected_json_dialog(self) -> None:
    if not self.conn:
        self._log("No database connection.")
        return

    idents = self._get_selected_curated_idents()
    if not idents:
        self._log("No curated selection. Select one or more rows in 'Curated Resources' first.")
        return

    dlg = Gtk.FileChooserNative.new("Export Selected (JSON)", self, Gtk.FileChooserAction.SAVE, "Export", "Cancel")
    dlg.set_current_name("selected.bundle.json")

    def _on_response(d, resp):
        if resp != Gtk.ResponseType.ACCEPT:
            d.destroy()
            return
        out = d.get_file().get_path()
        try:
            res = export_selected_bundle_json(self.conn, idents, out)
            self._log(res.message)
        except Exception as e:
            self._log(f"Export selected JSON failed: {e}")
            try:
                self._show_error_dialog("Export Selected (JSON)", str(e))
            except Exception:
                pass
        d.destroy()

    dlg.connect("response", _on_response)
    dlg.show()


def export_fhir_selected_xml_dialog(self) -> None:
    if not self.conn:
        self._log("No database connection.")
        return

    idents = self._get_selected_curated_idents()
    if not idents:
        self._log("No curated selection. Select one or more rows in 'Curated Resources' first.")
        return

    dialog = Gtk.Dialog(title="Export Selected (XML)", transient_for=self, modal=True)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Continue", Gtk.ResponseType.OK)

    box = dialog.get_content_area()
    box.set_spacing(6)
    box.append(Gtk.Label(label="XML export mode:", xalign=0))

    mode_dd = Gtk.DropDown.new_from_strings(["strict", "best-effort"])
    mode_dd.set_selected(1)
    box.append(mode_dd)

    def _on_dialog_response(dlg, resp):
        if resp != Gtk.ResponseType.OK:
            dlg.destroy()
            return

        model = mode_dd.get_model()
        idx = int(mode_dd.get_selected())
        mode_str = "best-effort"
        try:
            mode_str = model.get_item(idx).get_string()
        except Exception:
            pass
        dlg.destroy()

        save = Gtk.FileChooserNative.new("Save Bundle (XML)", self, Gtk.FileChooserAction.SAVE, "Save", "Cancel")
        save.set_current_name("selected.bundle.xml")

        def _on_save(sdlg, sresp):
            if sresp != Gtk.ResponseType.ACCEPT:
                sdlg.destroy()
                return
            out = sdlg.get_file().get_path()
            try:
                res = export_selected_bundle_xml(self.conn, idents, out, mode=mode_str)
                if not res.ok:
                    raise RuntimeError(res.message)
                self._log(res.message)
            except Exception as e:
                self._log(f"Export selected XML failed: {e}")
                try:
                    self._show_error_dialog("Export Selected (XML)", str(e))
                except Exception:
                    pass
            sdlg.destroy()

        save.connect("response", _on_save)
        save.show()

    dialog.connect("response", _on_dialog_response)
    dialog.show()


    def get_selected_uuid(self) -> str | None:
        idx = self.dd.get_selected()
        if self.allow_none:
            if idx <= 0:
                return None
            idx -= 1
        if idx < 0 or idx >= len(self.options):
            return None
        return self.options[idx][0]

    def set_selected_uuid(self, uuid: str | None):
        if uuid is None:
            self.dd.set_selected(0)
            return
        for i, (u, _label) in enumerate(self.options):
            if u == uuid:
                sel = i + (1 if self.allow_none else 0)
                self.dd.set_selected(sel)
                return
        self.dd.set_selected(0)


class _DesignationRow:
    def __init__(self, win: MDRWindow, des_uuid: str, language: str, des_type: str, text: str, is_pref: bool):
        self.win = win
        self.des_uuid = des_uuid
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_top(2)
        box.set_margin_bottom(2)

        self.lang = Gtk.Entry()
        self.lang.set_width_chars(7)
        self.lang.set_text(language)

        self.typ = Gtk.DropDown.new_from_strings(["preferred","synonym","abbrev"])
        win._select_in_dropdown(self.typ, des_type)

        self.text = Gtk.Entry()
        self.text.set_hexpand(True)
        self.text.set_text(text)

        self.pref = Gtk.CheckButton(label="preferred?")
        self.pref.set_active(is_pref)

        box.append(Gtk.Label(label="lang", xalign=0))
        box.append(self.lang)
        box.append(Gtk.Label(label="type", xalign=0))
        box.append(self.typ)
        box.append(Gtk.Label(label="text", xalign=0))
        box.append(self.text)
        box.append(self.pref)

        # selection on click
        controller = Gtk.GestureClick()
        controller.connect("pressed", self._on_pressed)
        box.add_controller(controller)

        box._row_obj = self  # type: ignore
        self.widget = box

    def _on_pressed(self, _gesture, _npress, _x, _y):
        self.win._selected_des_row = self


class _PVRow:
    def __init__(self, win: MDRWindow, pv_uuid: str, code: str, meaning: str, sort_order: int | None):
        self.win = win
        self.pv_uuid = pv_uuid
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_top(2)
        box.set_margin_bottom(2)

        self.code = Gtk.Entry()
        self.code.set_width_chars(8)
        self.code.set_text(code)

        self.meaning = Gtk.Entry()
        self.meaning.set_hexpand(True)
        self.meaning.set_text(meaning)

        self.sort = Gtk.Entry()
        self.sort.set_width_chars(6)
        self.sort.set_text("" if sort_order is None else str(sort_order))

        box.append(Gtk.Label(label="code", xalign=0))
        box.append(self.code)
        box.append(Gtk.Label(label="meaning", xalign=0))
        box.append(self.meaning)
        box.append(Gtk.Label(label="order", xalign=0))
        box.append(self.sort)

        controller = Gtk.GestureClick()
        controller.connect("pressed", self._on_pressed)
        box.add_controller(controller)

        box._row_obj = self  # type: ignore
        self.widget = box

    def _on_pressed(self, _gesture, _npress, _x, _y):
        self.win._selected_pv_row = self


class _ICRow:
    def __init__(self, win: MDRWindow, ic_uuid: str, scheme: str, item: str):
        self.win = win
        self.ic_uuid = ic_uuid
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl = Gtk.Label(label=f"{scheme} → {item}", xalign=0)
        lbl.set_hexpand(True)
        box.append(lbl)

        controller = Gtk.GestureClick()
        controller.connect("pressed", self._on_pressed)
        box.add_controller(controller)

        box._row_obj = self  # type: ignore
        self.widget = box

    def _on_pressed(self, _gesture, _npress, _x, _y):
        self.win._selected_ic_row = self

def _mdrwindow_refresh_fhir_views(self) -> None:
    # Curated
    try:
        # Update type dropdown choices
        types = [r[0] for r in self.conn.execute(
            "SELECT DISTINCT resource_type FROM fhir_curated_resource ORDER BY resource_type"
        ).fetchall()]
        if hasattr(self, "fhir_type_dd"):
            items = ["All"] + [t for t in types if t]
            self.fhir_type_dd.set_model(Gtk.StringList.new(items))
            wanted = self.curated_filter.resource_type or "All"
            try:
                self.fhir_type_dd.set_selected(items.index(wanted))
            except ValueError:
                self.fhir_type_dd.set_selected(0)

        sql, params = build_curated_query(self.curated_filter)
        rows = self.conn.execute(sql, params).fetchall()
        self._fhir_views["curated"].remove_all()
        for r in rows:
            self._fhir_views["curated"].append(Gtk.StringObject.new(
                f"{r[0]} | {r[1]} | v={r[2]} | conflict={r[3]} | {r[4]}"
            ))
    except Exception as e:
        self._log(f"FHIR curated view failed: {e}")

    # Conflicts
    try:
        rows = self.conn.execute(
            "SELECT resource_type, canonical_url, artifact_version, variant_count "
            "FROM v_fhir_artifact_conflicts ORDER BY variant_count DESC LIMIT 500"
        ).fetchall()
        self._fhir_views["conflicts"].remove_all()
        for r in rows:
            self._fhir_views["conflicts"].append(Gtk.StringObject.new(
                f"{r[0]} | {r[1]} | v={r[2]} | variants={r[3]}"
            ))
    except Exception as e:
        self._log(f"FHIR conflicts view failed: {e}")

    # Variants
    try:
        rows = self.conn.execute(
            "SELECT c.resource_type, IFNULL(c.canonical_url, c.logical_id) as ident, v.resource_sha256, v.occurrences "
            "FROM fhir_curated_variant v JOIN fhir_curated_resource c ON c.curated_id=v.curated_id "
            "ORDER BY v.occurrences DESC LIMIT 500"
        ).fetchall()
        self._fhir_views["variants"].remove_all()
        for r in rows:
            self._fhir_views["variants"].append(Gtk.StringObject.new(
                f"{r[0]} | {r[1]} | occ={r[3]} | sha={r[2][:12]}…"
            ))
    except Exception as e:
        self._log(f"FHIR variants view failed: {e}")

    # Runs
    try:
        rows = self.conn.execute(
            "SELECT run_id, started_ts, finished_ts, source_kind, source_name "
            "FROM fhir_ingest_run ORDER BY run_id DESC LIMIT 200"
        ).fetchall()
        self._fhir_views["runs"].remove_all()
        for r in rows:
            self._fhir_views["runs"].append(Gtk.StringObject.new(
                f"run={r[0]} | {r[3]} | {r[4]} | {r[1]} -> {r[2] or ''}"
            ))
    except Exception as e:
        self._log(f"FHIR runs view failed: {e}")


def _mdrwindow_update_selected_ui(self) -> None:
    """Update selected-count label and export button labels (curated multi-select)."""
    try:
        idents = []
        if hasattr(self, "_get_selected_curated_idents"):
            idents = self._get_selected_curated_idents()  # type: ignore
        n = len(idents)
        if hasattr(self, "fhir_selected_lbl"):
            self.fhir_selected_lbl.set_text(f"Selected: {n}")
        if hasattr(self, "btn_export_selected_json"):
            self.btn_export_selected_json.set_label(
                f"Export Selected JSON… ({n})" if n else "Export Selected JSON…"
            )
        if hasattr(self, "btn_export_selected_xml"):
            self.btn_export_selected_xml.set_label(
                f"Export Selected XML… ({n})" if n else "Export Selected XML…"
            )
    except Exception:
        # keep UI responsive; selection updates are best-effort
        pass


# ---- Method binding (hotfix for v0.0.x)
# Some helper functions are defined at module scope; bind them to MDRWindow to ensure
# instance methods exist even if the file was refactored incorrectly.
try:
    MDRWindow._on_filter_changed = _on_filter_changed  # type: ignore[name-defined]
    MDRWindow._clear_filters = _clear_filters  # type: ignore[name-defined]
    MDRWindow._get_selected_curated_idents = _get_selected_curated_idents  # type: ignore[name-defined]
    MDRWindow._get_selected_curated_ident = _get_selected_curated_ident  # type: ignore[name-defined]
    MDRWindow.export_fhir_selected_json_dialog = export_fhir_selected_json_dialog  # type: ignore[name-defined]
    MDRWindow.export_fhir_selected_xml_dialog = export_fhir_selected_xml_dialog  # type: ignore[name-defined]
    MDRWindow._refresh_fhir_views = _mdrwindow_refresh_fhir_views  # type: ignore[name-defined]
    MDRWindow._update_selected_ui = _mdrwindow_update_selected_ui  # type: ignore[name-defined]
except Exception:
    # If something is missing, fail gracefully; UI will surface the error via logs.
    pass


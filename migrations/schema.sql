-- ISO/IEC 11179 (Core+) – SQLite Schema
BEGIN;

CREATE TABLE IF NOT EXISTS context (
  uuid TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TRIGGER IF NOT EXISTS trg_context_updated
AFTER UPDATE ON context
FOR EACH ROW
BEGIN
  UPDATE context SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now')) WHERE uuid = OLD.uuid;
END;

CREATE TABLE IF NOT EXISTS registration_authority (
  uuid TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TRIGGER IF NOT EXISTS trg_ra_updated
AFTER UPDATE ON registration_authority
FOR EACH ROW
BEGIN
  UPDATE registration_authority SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now')) WHERE uuid = OLD.uuid;
END;

CREATE TABLE IF NOT EXISTS registrable_item (
  uuid TEXT PRIMARY KEY,
  item_type TEXT NOT NULL,
  preferred_name TEXT NOT NULL,
  definition TEXT NOT NULL,
  context_uuid TEXT,
  registration_authority_uuid TEXT,
  registration_status TEXT NOT NULL DEFAULT 'Candidate',
  administrative_status TEXT NOT NULL DEFAULT 'Draft',
  steward TEXT,
  submitting_organization TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),

  CONSTRAINT fk_item_context
    FOREIGN KEY (context_uuid) REFERENCES context(uuid) ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_item_ra
    FOREIGN KEY (registration_authority_uuid) REFERENCES registration_authority(uuid) ON UPDATE CASCADE ON DELETE SET NULL,

  CONSTRAINT chk_item_type
    CHECK (item_type IN (
      'DATA_ELEMENT','DATA_ELEMENT_CONCEPT','VALUE_DOMAIN','CONCEPTUAL_DOMAIN',
      'OBJECT_CLASS','PROPERTY','REPRESENTATION_CLASS',
      'CLASSIFICATION_SCHEME','CLASSIFICATION_ITEM'
    )),
  CONSTRAINT chk_reg_status
    CHECK (registration_status IN ('Candidate','Recorded','Qualified','Standard','Retired')),
  CONSTRAINT chk_admin_status
    CHECK (administrative_status IN ('Draft','Released','Superseded','Deprecated'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_registrable_item_type_name
  ON registrable_item(item_type, preferred_name);

CREATE TRIGGER IF NOT EXISTS trg_registrable_item_updated
AFTER UPDATE ON registrable_item
FOR EACH ROW
BEGIN
  UPDATE registrable_item
    SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    WHERE uuid = OLD.uuid;
END;

-- -------- Core entities --------
CREATE TABLE IF NOT EXISTS conceptual_domain (
  uuid TEXT PRIMARY KEY,
  description TEXT,
  CONSTRAINT fk_cd_item FOREIGN KEY (uuid) REFERENCES registrable_item(uuid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS representation_class (
  uuid TEXT PRIMARY KEY,
  CONSTRAINT fk_rc_item FOREIGN KEY (uuid) REFERENCES registrable_item(uuid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS object_class (
  uuid TEXT PRIMARY KEY,
  CONSTRAINT fk_oc_item FOREIGN KEY (uuid) REFERENCES registrable_item(uuid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS property (
  uuid TEXT PRIMARY KEY,
  CONSTRAINT fk_prop_item FOREIGN KEY (uuid) REFERENCES registrable_item(uuid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS data_element_concept (
  uuid TEXT PRIMARY KEY,
  object_class_uuid TEXT NOT NULL,
  property_uuid TEXT NOT NULL,
  conceptual_domain_uuid TEXT,
  CONSTRAINT fk_dec_item FOREIGN KEY (uuid) REFERENCES registrable_item(uuid) ON DELETE CASCADE,
  CONSTRAINT fk_dec_oc FOREIGN KEY (object_class_uuid) REFERENCES object_class(uuid) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_dec_prop FOREIGN KEY (property_uuid) REFERENCES property(uuid) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_dec_cd FOREIGN KEY (conceptual_domain_uuid) REFERENCES conceptual_domain(uuid) ON UPDATE CASCADE ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_dec_oc ON data_element_concept(object_class_uuid);
CREATE INDEX IF NOT EXISTS ix_dec_prop ON data_element_concept(property_uuid);

CREATE TABLE IF NOT EXISTS value_domain (
  uuid TEXT PRIMARY KEY,
  datatype TEXT NOT NULL DEFAULT 'string',
  unit_of_measure TEXT,
  max_length INTEGER,
  format TEXT,
  conceptual_domain_uuid TEXT,
  representation_class_uuid TEXT,
  CONSTRAINT fk_vd_item FOREIGN KEY (uuid) REFERENCES registrable_item(uuid) ON DELETE CASCADE,
  CONSTRAINT fk_vd_cd FOREIGN KEY (conceptual_domain_uuid) REFERENCES conceptual_domain(uuid) ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_vd_rc FOREIGN KEY (representation_class_uuid) REFERENCES representation_class(uuid) ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT chk_vd_datatype CHECK (datatype IN ('string','integer','decimal','date','datetime','boolean','code'))
);

CREATE TABLE IF NOT EXISTS data_element (
  uuid TEXT PRIMARY KEY,
  data_element_concept_uuid TEXT NOT NULL,
  value_domain_uuid TEXT NOT NULL,
  CONSTRAINT fk_de_item FOREIGN KEY (uuid) REFERENCES registrable_item(uuid) ON DELETE CASCADE,
  CONSTRAINT fk_de_dec FOREIGN KEY (data_element_concept_uuid) REFERENCES data_element_concept(uuid) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_de_vd FOREIGN KEY (value_domain_uuid) REFERENCES value_domain(uuid) ON UPDATE CASCADE ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_de_dec ON data_element(data_element_concept_uuid);
CREATE INDEX IF NOT EXISTS ix_de_vd ON data_element(value_domain_uuid);

-- -------- Version history --------
CREATE TABLE IF NOT EXISTS item_version (
  uuid TEXT PRIMARY KEY,
  item_uuid TEXT NOT NULL,
  version INTEGER NOT NULL,
  changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  changed_by TEXT,
  change_note TEXT,
  CONSTRAINT fk_iv_item FOREIGN KEY (item_uuid) REFERENCES registrable_item(uuid) ON DELETE CASCADE,
  CONSTRAINT ux_item_version UNIQUE(item_uuid, version)
);

-- -------- Core+ : Designations --------
-- Multiple designations per item, by language and context.
CREATE TABLE IF NOT EXISTS designation (
  uuid TEXT PRIMARY KEY,
  item_uuid TEXT NOT NULL,
  context_uuid TEXT,
  language_tag TEXT NOT NULL DEFAULT 'und', -- BCP-47 tag, e.g. de, en, de-DE
  designation TEXT NOT NULL,
  designation_type TEXT NOT NULL DEFAULT 'synonym', -- preferred|synonym|abbrev
  is_preferred INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  CONSTRAINT fk_des_item FOREIGN KEY (item_uuid) REFERENCES registrable_item(uuid) ON DELETE CASCADE,
  CONSTRAINT fk_des_ctx FOREIGN KEY (context_uuid) REFERENCES context(uuid) ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT chk_des_type CHECK (designation_type IN ('preferred','synonym','abbrev')),
  CONSTRAINT chk_des_pref CHECK (is_preferred IN (0,1))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_designation_unique
  ON designation(item_uuid, language_tag, designation_type, designation);

CREATE TRIGGER IF NOT EXISTS trg_designation_updated
AFTER UPDATE ON designation
FOR EACH ROW
BEGIN
  UPDATE designation SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now')) WHERE uuid = OLD.uuid;
END;

-- -------- Core+ : Permissible Values (enumerated VD) --------
CREATE TABLE IF NOT EXISTS permissible_value (
  uuid TEXT PRIMARY KEY,
  value_domain_uuid TEXT NOT NULL,
  code TEXT NOT NULL,
  meaning TEXT NOT NULL,
  sort_order INTEGER,
  valid_from TEXT,
  valid_to TEXT,
  CONSTRAINT fk_pv_vd FOREIGN KEY (value_domain_uuid) REFERENCES value_domain(uuid) ON DELETE CASCADE,
  CONSTRAINT ux_pv_code UNIQUE(value_domain_uuid, code)
);
CREATE INDEX IF NOT EXISTS ix_pv_vd ON permissible_value(value_domain_uuid);

-- -------- Core+ : Classification schemes --------
CREATE TABLE IF NOT EXISTS classification_scheme (
  uuid TEXT PRIMARY KEY,
  scheme_uri TEXT,
  CONSTRAINT fk_cs_item FOREIGN KEY (uuid) REFERENCES registrable_item(uuid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS classification_item (
  uuid TEXT PRIMARY KEY,
  scheme_uuid TEXT NOT NULL,
  parent_uuid TEXT,
  item_code TEXT,
  CONSTRAINT fk_ci_item FOREIGN KEY (uuid) REFERENCES registrable_item(uuid) ON DELETE CASCADE,
  CONSTRAINT fk_ci_scheme FOREIGN KEY (scheme_uuid) REFERENCES classification_scheme(uuid) ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_ci_parent FOREIGN KEY (parent_uuid) REFERENCES classification_item(uuid) ON UPDATE CASCADE ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_ci_scheme ON classification_item(scheme_uuid);
CREATE INDEX IF NOT EXISTS ix_ci_parent ON classification_item(parent_uuid);

CREATE TABLE IF NOT EXISTS item_classification (
  uuid TEXT PRIMARY KEY,
  item_uuid TEXT NOT NULL,
  classification_item_uuid TEXT NOT NULL,
  assigned_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  assigned_by TEXT,
  CONSTRAINT fk_ic_item FOREIGN KEY (item_uuid) REFERENCES registrable_item(uuid) ON DELETE CASCADE,
  CONSTRAINT fk_ic_ci FOREIGN KEY (classification_item_uuid) REFERENCES classification_item(uuid) ON DELETE CASCADE,
  CONSTRAINT ux_ic UNIQUE(item_uuid, classification_item_uuid)
);
CREATE INDEX IF NOT EXISTS ix_ic_item ON item_classification(item_uuid);
CREATE INDEX IF NOT EXISTS ix_ic_ci ON item_classification(classification_item_uuid);

COMMIT;

-- ---------------------------------------------------------------------------
-- FHIR R4 Mixed-Ingest Layer (minimal, stable)
-- Goals:
--  - Record ingest runs (bundle/package)
--  - Store raw bundle/resources (JSON as TEXT)
--  - Maintain curated identities + variants + conflict flag
-- ---------------------------------------------------------------------------

BEGIN;

CREATE TABLE IF NOT EXISTS fhir_ingest_run (
  run_id INTEGER PRIMARY KEY,
  started_ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  finished_ts TEXT,
  source_name TEXT NOT NULL,
  source_kind TEXT NOT NULL CHECK (source_kind IN ('bundle','package')),
  fhir_major TEXT NOT NULL DEFAULT 'R4' CHECK (fhir_major IN ('R4')),
  partition_key TEXT
);

CREATE INDEX IF NOT EXISTS idx_fhir_ingest_run_started_ts ON fhir_ingest_run(started_ts);

CREATE TABLE IF NOT EXISTS fhir_raw_bundle (
  bundle_id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES fhir_ingest_run(run_id) ON DELETE CASCADE,
  bundle_type TEXT,
  bundle_sha256 TEXT,
  bundle_json TEXT
);

CREATE TABLE IF NOT EXISTS fhir_raw_resource (
  raw_id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES fhir_ingest_run(run_id) ON DELETE CASCADE,
  bundle_id INTEGER REFERENCES fhir_raw_bundle(bundle_id) ON DELETE SET NULL,

  full_url TEXT,

  resource_type TEXT NOT NULL,
  logical_id TEXT,
  canonical_url TEXT,
  artifact_version TEXT,

  meta_version_id TEXT,
  meta_last_updated TEXT,

  resource_sha256 TEXT NOT NULL,
  resource_json TEXT NOT NULL,

  first_seen_ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),

  UNIQUE(run_id, resource_sha256)
);

CREATE INDEX IF NOT EXISTS idx_fhir_raw_resource_run_id ON fhir_raw_resource(run_id);
CREATE INDEX IF NOT EXISTS idx_fhir_raw_resource_type_id ON fhir_raw_resource(resource_type, logical_id);
CREATE INDEX IF NOT EXISTS idx_fhir_raw_resource_canonical ON fhir_raw_resource(resource_type, canonical_url, artifact_version);

CREATE TABLE IF NOT EXISTS fhir_curated_resource (
  curated_id INTEGER PRIMARY KEY,

  resource_type TEXT NOT NULL,
  logical_id TEXT,
  canonical_url TEXT,
  artifact_version TEXT,
  partition_key TEXT,

  current_sha256 TEXT NOT NULL,
  has_conflict INTEGER NOT NULL DEFAULT 0 CHECK (has_conflict IN (0,1)),

  first_seen_ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  last_seen_ts  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),

  CHECK (
    (canonical_url IS NOT NULL)
    OR
    (logical_id IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_fhir_curated_type_logical ON fhir_curated_resource(resource_type, logical_id);
CREATE INDEX IF NOT EXISTS idx_fhir_curated_type_canonical ON fhir_curated_resource(resource_type, canonical_url, artifact_version);

CREATE TABLE IF NOT EXISTS fhir_curated_variant (
  curated_id INTEGER NOT NULL REFERENCES fhir_curated_resource(curated_id) ON DELETE CASCADE,
  resource_sha256 TEXT NOT NULL,
  occurrences INTEGER NOT NULL DEFAULT 1 CHECK (occurrences >= 1),
  first_seen_run_id INTEGER NOT NULL REFERENCES fhir_ingest_run(run_id) ON DELETE RESTRICT,
  last_seen_run_id INTEGER NOT NULL REFERENCES fhir_ingest_run(run_id) ON DELETE RESTRICT,
  note TEXT,
  PRIMARY KEY (curated_id, resource_sha256)
);

CREATE TABLE IF NOT EXISTS fhir_raw_to_curated (
  raw_id INTEGER PRIMARY KEY REFERENCES fhir_raw_resource(raw_id) ON DELETE CASCADE,
  curated_id INTEGER NOT NULL REFERENCES fhir_curated_resource(curated_id) ON DELETE CASCADE,
  linked_ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS fhir_reference_edge (
  edge_id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES fhir_ingest_run(run_id) ON DELETE CASCADE,
  from_raw_id INTEGER NOT NULL REFERENCES fhir_raw_resource(raw_id) ON DELETE CASCADE,
  from_path TEXT NOT NULL,
  to_reference TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fhir_reference_edge_run_id ON fhir_reference_edge(run_id);

CREATE VIEW IF NOT EXISTS v_fhir_artifact_conflicts AS
SELECT
  r.resource_type,
  r.canonical_url,
  r.artifact_version,
  COUNT(DISTINCT r.resource_sha256) AS variant_count
FROM fhir_raw_resource r
WHERE r.canonical_url IS NOT NULL
GROUP BY r.resource_type, r.canonical_url, r.artifact_version
HAVING COUNT(DISTINCT r.resource_sha256) > 1;

COMMIT;

# FHIR-MDR (ISO/IEC 11179-inspired) — v0.0.1

FHIR-MDR is a lightweight **Meta Data Repository (MDR)** for managing **FHIR R4 conformance artefacts**
(e.g., StructureDefinitions, ValueSets, CodeSystems, etc.) with a pragmatic ISO/IEC 11179-inspired approach.

**Scope:** This is **not** a patient data store. It is a repository for **artefacts, provenance, variants, conflicts,
and reproducible exports**.

> Status: **Early preview (v0.0.1)** — functional, test-backed core, packaging/CI still evolving.

## Key ideas

- Treat artefacts as governed metadata objects: **identity**, **provenance**, **version**, **relationships**
- Ingest pipeline: **Run → Raw → Curated**
  - **Run**: import session (source, time, scope/partition)
  - **Raw**: immutable original (content-addressed via hash)
  - **Curated**: “current” selection + **variants** + **conflict marker** (no silent overwrite)

## Features

- Import:
  - FHIR **Bundle** import (JSON / XML)
  - FHIR **Package** import (tgz) and directory import
- Views:
  - Curated resources (with search/filter)
  - Variants & conflicts (conflict-first workflow)
- Export:
  - Export curated **Bundle** (JSON / XML)
  - **Multi-select** export (select N curated artefacts → export one bundle)
- Quality:
  - Unit tests for schema/query/export helpers
  - `doctor.py` / `doctor.sh` self-check scripts

## Quickstart (Linux / GNOME)

### 1) Dependencies
- Python 3.10+ recommended
- GTK4 + PyGObject (gi)

On Debian-based systems:
- Install GTK4 + PyGObject packages (names vary by distro release)

### 2) Run self-check
```bash
python3 doctor.py
# or:
./doctor.sh
```

### 3) Start the GUI
```bash
python3 -m mdr_gtk --db mdr.sqlite
```

If the database file does not exist, the schema is applied automatically.

## CLI helpers

Examples (paths may differ depending on your setup):

```bash
# Import a FHIR package (tgz)
python3 -m mdr_gtk.scripts.import_fhir_package --db mdr.sqlite path/to/package.tgz

# Import a directory containing package files
python3 -m mdr_gtk.scripts.import_fhir_package_dir --db mdr.sqlite path/to/package_dir

# Import a FHIR bundle (JSON or XML)
python3 -m mdr_gtk.scripts.import_fhir_bundle --db mdr.sqlite path/to/bundle.json
python3 -m mdr_gtk.scripts.import_fhir_bundle --db mdr.sqlite path/to/bundle.xml

### Import (FHIR conformance artefacts)

Import a FHIR Bundle (JSON or XML):

python3 -m mdr_gtk.scripts.import_fhir_bundle --db mdr.sqlite examples/bundle.json
python3 -m mdr_gtk.scripts.import_fhir_bundle --db mdr.sqlite examples/bundle.xml

### Import an FHIR package archive (.tgz):

python3 -m mdr_gtk.scripts.import_fhir_package --db mdr.sqlite path/to/package.tgz
```

## Search/Filter (Curated view)

- Filter by `resourceType`
- Search by partial match in `canonical_url` or `logical_id`
- `conflicts only` toggle
- Limit results for performance

## Limitations (v0.0.1)

- Windows/macOS distribution is not yet “one-click”. See `packaging/` (skeleton).
- GUI is functional but not fully covered by E2E UI tests.
- Conformance validation against official FHIR validators is not yet integrated.

## Roadmap (short)

- CI builds (Linux/Windows/macOS)
- Validator integration (optional)
- Dependency graph / IG relationships UI
- More regression tests (import/merge/conflict scenarios)

## License

GNU GPL v3.0 (GPL-3.0-only). See `LICENSE`.

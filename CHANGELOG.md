# Changelog

## v0.0.1
- ISO/IEC 11179-inspired FHIR artefact repository (Run → Raw → Curated)
- Import: FHIR bundles (JSON/XML), FHIR packages (tgz/dir)
- Views: Curated, Variants, Conflicts
- Search/filter + multi-select export (JSON/XML)
- Tests for core helpers + doctor/self-check
- Packaging skeleton for Windows/macOS (documentation + scripts)


## v0.0.2
- Fix GUI startup: restore missing _RefDropDown helper


## v0.0.3 - 2026-01-22

### Added
- FHIR Bundle XML import support (CLI + ingest layer).
- XML bundle parsing for conformance artefacts (Bundle.entry.resource.*).

### Changed
- Import CLI now auto-detects JSON vs XML bundles and routes to the correct importer.
- Test suite extended to cover JSON + XML bundle import, conflict detection, and `last_seen_ts` sorting.

### Fixed
- Stabilized ingest tests (unique test bundle filenames/IDs) to prevent accidental overwrites during test runs.

## v0.0.4
- GUI Services/Fassade (routing)
- Export Services
- Strict-clean GUI Test
- ResourceWarning Hardening
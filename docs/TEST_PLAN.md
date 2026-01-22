# Test Plan (Backend-first, no GUI E2E)

This repository is a *FHIR conformance artefact MDR* (not a patient store).
We test the *backend behaviours* that must always hold, independent of the GTK UI.

## Principles

- **No GUI E2E** in unit tests (keeps tests stable & CI-friendly).
- Prefer **black-box** tests via CLI scripts where possible (importers), then verify DB state.
- When a bug is found: **add a failing test first**, then fix the bug, keep the test.

## Core behaviours to lock down

### A) Schema
- Applying schema to a fresh DB works.
- Applying schema again is idempotent (no errors).

### B) Ingest: Run → Raw → Curated
- Import Bundle (JSON) creates curated entries.
- Import Bundle (XML) creates curated entries.
- Import Package (tgz) creates curated entries.

### C) Dedupe & Conflicts
- Importing the *same artefact content* twice does not duplicate raw payloads (hash dedupe).
- Importing *same canonical URL but different bytes* creates an explicit conflict (`has_conflict=1`) and variants ≥ 2.

### D) Query semantics
- Curated list can be sorted by `last_seen_ts DESC`.
- Filters (resourceType / conflicts-only / search text) behave deterministically.

### E) Export (future tests)
- Multi-select export produces a bundle (JSON & XML), containing exactly the selected curated artefacts.

## How to run locally

```bash
./run_tests.sh
# or
python3 -m unittest -v
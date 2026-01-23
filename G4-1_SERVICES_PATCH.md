# G4-1 Service-Kapselung (Patch)

Dieses Patch führt eine kleine Service-Schicht ein, damit GUI/CLI keine
Schema-/DB-Lifecycle-Logik duplizieren müssen.

## Enthalten
- `mdr_gtk/services.py`
  - `ensure_schema_applied(conn)` (zentral)
  - `db_conn(db_path)` Context-Manager (öffnet + schließt)
  - `MDRServices` Facade für GUI (import bundle/package)
- CLI-Skripte nutzen nun `ensure_schema_applied` aus services
- GUI (`mdr_gtk/ui.py`) nutzt nun `ensure_schema_applied` statt Inline-Checks
- Neuer Test: `tests/test_services_layer.py`

## Einspielen
Im Repo-Root:

```bash
unzip -o FHIR-MDR_G4-1_services_capsule_patch.zip -d .
python -m unittest -v
```


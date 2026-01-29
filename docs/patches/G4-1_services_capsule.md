# G4-1 – Services‑Kapselung (GUI → Services) – Patchset Notizen

**Status:** aktiv (soll ab v0.0.4 Bestandteil von `main` sein)

Dieses Dokument ersetzt die ad‑hoc Patch‑Readmes im Repository‑Root (siehe unten „Obsolete Dateien“).

## Ziel

- GUI‑Actions werden **über eine Services‑Schicht** geroutet, damit Logik testbar ist, ohne GTK‑Klick‑Automation.
- SQLite‑Locks / `ResourceWarning` wurden an kritischen Stellen entschärft (kurzlebige Connections, konsequentes Schließen).

## Inhalt (G4‑1 Teilaufgaben)

### G4‑1.0 / Basis
- Einführung einer Services‑Kapselung und `GUIServiceFacade` als zentrale Routing‑Schicht.
- Bestehende Tests bleiben grün; Smoke‑Tests der GUI bleiben bewusst minimal.

### G4‑1.1
- Auswahl von 3 kritischen GUI‑Funktionen und Routing auf Services.
- Tests: Action→Service (Mock/Spy) ohne GTK Automation.

### G4‑1.2 – Search/Filter
- Suche/Filter‑Logik wird über Services auf DB‑Queries geroutet.
- Tests: Routing + Query‑Builder‑Abdeckung.

### G4‑1.3 – Export
- Export All / Curated Set / Selected über Export‑Services.
- Tests: Export‑Services + GUI‑Routing‑Tests.

### G4‑1.4 – Refresh Views
- „Refresh/Reload Views“ (Varianten/Conflicts/Typenlisten) über Services.
- Tests: Refresh‑Services + GUI‑Routing‑Tests.

## Validierung

Minimal (sollte lokal und in CI laufen):

```bash
python -m unittest -v
PYTHONTRACEMALLOC=25 python -W error::ResourceWarning -m unittest -v
```

Optional „Runtime/GUI strict‑clean“ (kein GTK‑Click‑Test, nur Lebenszyklus + clean shutdown):

```bash
PYTHONTRACEMALLOC=25 PYTHONWARNINGS=error::ResourceWarning python - <<'PY'
import os, tempfile, inspect
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from mdr_gtk.app import MDRApp

# robust: __init__ Signatur prüfen
sig = inspect.signature(MDRApp.__init__)
kwargs = {}
if 'db_path' in sig.parameters:
    kwargs['db_path'] = os.path.join(tempfile.gettempdir(), 'mdr_strict_clean.sqlite')

app = MDRApp(**kwargs)
app.register(None)
app.activate()
for w in list(app.get_windows()):
    w.close()
app.quit()

print('GUI strict-clean OK')
PY
```

## Obsolete Dateien (werden behalten, aber als „obsolete“ markiert)

- `G4-1.1_PATCH_README.md`
- `G4-1_SERVICES_PATCH.md`

Beide Dateien sollten künftig **nicht mehr gepflegt** werden. Bitte nur dieses Dokument aktualisieren.

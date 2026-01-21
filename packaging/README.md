# Packaging (Skeleton)

Ziel: reproduzierbare Builds für Linux / Windows / macOS.

Hinweis: GTK4 + PyGObject zu bundlen ist möglich, aber benötigt jeweils
die passende Runtime (DLLs/dylibs, gsettings schemas, loaders).
Dieses Verzeichnis liefert **Build-Skelette** und eine klare Struktur.

- `windows/` – MSYS2 + PyInstaller
- `macos/` – Homebrew + PyInstaller (App Bundle)
- `common/` – gemeinsame Hinweise / Spec-Vorlagen

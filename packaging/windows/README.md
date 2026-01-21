# Windows Build (MSYS2 + PyInstaller) – Skeleton

## 1) Voraussetzungen
- MSYS2 installieren
- In "MSYS2 MinGW x64" Shell:
  - `pacman -Syu`
  - `pacman -S mingw-w64-x86_64-python mingw-w64-x86_64-gtk4 mingw-w64-x86_64-python-gobject`
  - `pip install -U pip pyinstaller`

## 2) Build
Siehe `build.ps1` (Skeleton). Ziel ist eine portable Distribution, die GTK4 Runtime enthält.

## 3) Stolpersteine
- GTK DLLs + schemas + loaders müssen mit ausgeliefert werden.
- `GI_TYPELIB_PATH`, `GSETTINGS_SCHEMA_DIR` ggf. setzen.

\
# Skeleton: Windows build using MSYS2 MinGW64 + PyInstaller
# Run in a PowerShell where MSYS2 mingw64 python is on PATH.

$ErrorActionPreference = "Stop"
python --version

# Install deps (example)
# pip install -U pip pyinstaller

# Build
pyinstaller --noconfirm --clean --name mdr_gtk ^
  --onefile ^
  -m mdr_gtk

Write-Host "NOTE: For GTK apps, you typically need a one-dir build and to bundle GTK runtime files."

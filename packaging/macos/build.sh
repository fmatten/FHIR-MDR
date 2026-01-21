#!/usr/bin/env bash
set -euo pipefail

python3 --version
# pip install -U pip pyinstaller

pyinstaller --noconfirm --clean --name mdr_gtk --windowed -m mdr_gtk

echo "NOTE: For GTK apps, bundle dylibs/resources (schemas/loaders). Consider one-dir builds."

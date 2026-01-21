#!/usr/bin/env bash
set -euo pipefail

echo "MDR GTK Doctor (G2.1)"
echo "---------------------"

need_cmd() {
  local c="$1"
  if ! command -v "$c" >/dev/null 2>&1; then
    echo "FAIL: missing command: $c"
    return 1
  fi
  echo "OK: $c"
}

need_cmd python3
need_cmd sqlite3 || true
need_cmd pkg-config || true

echo
python3 -V

echo
echo "Checking PyGObject / GTK..."
python3 - <<'PY'
import sys
try:
    import gi
    print("OK: gi import")
except Exception as e:
    print("FAIL: gi import ->", e)
    sys.exit(2)

try:
    gi.require_version("Gtk","4.0")
    from gi.repository import Gtk
    print("OK: Gtk 4 import")
except Exception as e:
    print("FAIL: Gtk 4 import ->", e)
    sys.exit(3)
PY

echo
echo "Checking schema file..."
if [ -f "migrations/schema.sql" ]; then
  echo "OK: migrations/schema.sql"
else
  echo "FAIL: migrations/schema.sql missing"
  exit 4
fi

echo
echo "Checking basic import..."
python3 - <<'PY'
try:
    import mdr_gtk
    import mdr_gtk.app
    import mdr_gtk.ui
    print("OK: imports mdr_gtk/app/ui")
except Exception as e:
    print("FAIL: import ->", e)
    raise
PY

echo
echo "Doctor finished: OK"

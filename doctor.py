#!/usr/bin/env python3
from __future__ import annotations

import importlib
import platform
import sys
from pathlib import Path

def check_module(name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(name)
        return True, f"OK: python module {name}"
    except Exception as e:
        return False, f"FAIL: python module {name} -> {e}"

def main() -> int:
    print("MDR GTK Doctor (cross-platform)")
    print("------------------------------")
    print("Python:", sys.version.split()[0])
    print("Platform:", platform.platform())
    print()

    ok_all = True
    for mod in ["mdr_gtk", "mdr_gtk.app", "mdr_gtk.ui"]:
        ok, msg = check_module(mod)
        print(msg)
        ok_all = ok_all and ok

    # gi/GTK checks (optional on non-GUI environments)
    ok, msg = check_module("gi")
    print(msg)
    if ok:
        try:
            import gi
            gi.require_version("Gtk", "4.0")
            from gi.repository import Gtk  # noqa
            print("OK: Gtk 4 import")
        except Exception as e:
            print("FAIL: Gtk 4 import ->", e)
            ok_all = False

    schema = Path("migrations/schema.sql")
    if schema.exists():
        print("OK: migrations/schema.sql")
    else:
        print("FAIL: migrations/schema.sql missing")
        ok_all = False

    return 0 if ok_all else 2

if __name__ == "__main__":
    raise SystemExit(main())

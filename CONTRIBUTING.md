# Contributing

Thanks for your interest in contributing!

## Development setup
- Python 3.10+ recommended
- GTK4 + PyGObject (gi)
- Debian/Ubuntu (Beispiel):
  - python3-gi, gir1.2-gtk-4.0, libgtk-4-1 (und ggf. Build deps, falls pip PyGObject genutzt wird)
- Dann:
  - pip install -e .
  - python -m unittest -v
  - Optional: PYTHONWARNINGS=error::ResourceWarning


Run checks:
```bash
python3 doctor.py
python3 -m unittest discover -s tests -p "test_*.py"
```

## What to contribute
Good first contributions:
- Improve docs (README, screenshots, architecture notes)
- Add regression tests for import/merge/conflict cases
- CI workflows (Linux/Windows/macOS)
- Packaging improvements for Windows/macOS

## Style
- Keep changes small and test-backed where possible.
- Prefer pure-Python logic in helper modules; keep UI thin.

## License
By contributing, you agree that your contributions are licensed under GPL-3.0-only.

from __future__ import annotations

import os


def read_text(rel_path: str) -> str:
    """
    Read a repository file by path relative to repo root.
    """
    here = os.path.dirname(__file__)
    repo_root = os.path.abspath(os.path.join(here, os.pardir))
    candidate = os.path.join(repo_root, rel_path)
    if os.path.exists(candidate):
        with open(candidate, "r", encoding="utf-8") as f:
            return f.read()
    raise FileNotFoundError(f"Cannot find {rel_path}")

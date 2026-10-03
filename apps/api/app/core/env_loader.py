"""Load repo `.env` into os.environ before config/database (dev-friendly persistence)."""
from __future__ import annotations

import os
from pathlib import Path

from .config import ROOT


def load_env_file() -> Path | None:
    path = ROOT / ".env"
    if not path.is_file():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val
    return path

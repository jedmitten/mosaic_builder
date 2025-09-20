from __future__ import annotations

from pathlib import Path


def get_project_root() -> Path:
    return Path(__file__).parent.parent

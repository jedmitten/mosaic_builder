import os
from pathlib import Path

from PIL import Image

_ART_DIR = os.environ.get("MB_ARTIFACTS", "").strip()


def artifacts_dir() -> Path | None:
    return Path(_ART_DIR) if _ART_DIR else None


def save_png(img: Image.Image, name: str) -> Path | None:
    """Save test image if MB_ARTIFACTS is set; return path or None."""
    outdir = artifacts_dir()
    if not outdir:
        return None
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{name}.png"
    path.unlink(missing_ok=True)
    img.save(path)
    return path

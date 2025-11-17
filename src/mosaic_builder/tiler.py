"""Character tile extraction utilities."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageOps


SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def load_image(path: Path) -> Image.Image:
    """Load an image with EXIF orientation respected."""
    img = Image.open(path)
    return ImageOps.exif_transpose(img).convert("RGB")


def texture_score(tile: Image.Image) -> float:
    arr = np.asarray(tile.convert("L"), dtype=np.float32)
    if not arr.size:
        return 0.0
    variance = float(arr.var())
    gx = np.abs(np.diff(arr, axis=1)).mean() if arr.shape[1] > 1 else 0.0
    gy = np.abs(np.diff(arr, axis=0)).mean() if arr.shape[0] > 1 else 0.0
    return variance + 0.5 * (gx + gy)


def _candidate_offsets(length: int, side: int) -> Iterable[int]:
    if length == side:
        return [0]
    offsets = {0, max(0, (length - side) // 2), length - side}
    return sorted(offsets)


def extract_character_tiles(img: Image.Image, max_tiles: int = 3) -> list[TileCrop]:
    """Extract up to `max_tiles` square crops ranked by texture."""
    base = ImageOps.exif_transpose(img).convert("RGB")
    w, h = base.size
    side = min(w, h)
    if side == 0:
        return []

    candidates: list[TileCrop] = []
    if w >= h:
        for x in _candidate_offsets(w, side):
            crop = base.crop((x, 0, x + side, side))
            candidates.append(TileCrop(image=crop, box=(x, 0, x + side, side), score=texture_score(crop)))
    if h > w or not candidates:
        for y in _candidate_offsets(h, side):
            crop = base.crop((0, y, side, y + side))
            candidates.append(TileCrop(image=crop, box=(0, y, side, y + side), score=texture_score(crop)))

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[:max_tiles]


def resize_tile(tile: Image.Image, side: int) -> Image.Image:
    return ImageOps.fit(tile, (side, side), method=Image.Resampling.LANCZOS)


def mean_rgb(tile: Image.Image) -> tuple[float, float, float]:
    arr = np.asarray(tile, dtype=np.float32)
    r = float(arr[..., 0].mean())
    g = float(arr[..., 1].mean())
    b = float(arr[..., 2].mean())
    return r, g, b


def tile_png_bytes(tile: Image.Image) -> bytes:
    buf = io.BytesIO()
    tile.save(buf, format="PNG")
    return buf.getvalue()


@dataclass(frozen=True)
class TileCrop:
    image: Image.Image
    box: tuple[int, int, int, int]
    score: float


def iter_gallery_images(images_dir: Path) -> Iterable[Path]:
    for path in sorted(images_dir.iterdir()):
        if path.suffix.lower() in SUPPORTED_EXTS and path.is_file():
            yield path

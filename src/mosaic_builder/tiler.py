"""Character tile extraction utilities."""

from __future__ import annotations

import io
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

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
    """Extract up to `max_tiles` square crops ranked by texture.

    Caller is responsible for EXIF transpose (see load_image).
    """
    w, h = img.size
    side = min(w, h)
    if side == 0:
        return []

    candidates: list[TileCrop] = []
    if w >= h:
        for x in _candidate_offsets(w, side):
            crop = img.crop((x, 0, x + side, side))
            candidates.append(TileCrop(image=crop, box=(x, 0, x + side, side), score=texture_score(crop)))
    if h > w or not candidates:
        for y in _candidate_offsets(h, side):
            crop = img.crop((0, y, side, y + side))
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


def _srgb_to_lab(arr_rgb: np.ndarray) -> np.ndarray:
    """Convert an (H, W, 3) sRGB uint8 array to CIE-LAB float32.

    Pipeline: sRGB [0-255] → linear RGB → XYZ (D65) → LAB.
    """
    # Linearize sRGB
    rgb = arr_rgb.astype(np.float32) / 255.0
    mask = rgb > 0.04045
    rgb = np.where(mask, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)

    # sRGB → XYZ (D65 white point)
    # fmt: off
    M = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ], dtype=np.float32)
    # fmt: on
    xyz = rgb @ M.T

    # Normalize by D65 white point
    xyz[..., 0] /= 0.95047
    xyz[..., 2] /= 1.08883

    # XYZ → LAB
    epsilon = 0.008856
    kappa = 903.3
    mask = xyz > epsilon
    f = np.where(mask, np.cbrt(xyz), (kappa * xyz + 16.0) / 116.0)

    L = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def mean_lab(tile: Image.Image) -> tuple[float, float, float]:
    """Compute mean CIE-LAB values for a tile (sRGB input)."""
    arr = np.asarray(tile.convert("RGB"), dtype=np.uint8)
    lab = _srgb_to_lab(arr)
    return float(lab[..., 0].mean()), float(lab[..., 1].mean()), float(lab[..., 2].mean())


def delta_e(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    """CIE76 Delta-E distance between two LAB color tuples."""
    return math.sqrt((lab1[0] - lab2[0]) ** 2 + (lab1[1] - lab2[1]) ** 2 + (lab1[2] - lab2[2]) ** 2)


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

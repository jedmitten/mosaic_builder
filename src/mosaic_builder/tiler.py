"""Character tile extraction utilities."""

from __future__ import annotations

import io
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from skimage.filters import threshold_otsu, window

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

#: Half-saturation constant for color_contrast_score's x/(x+k) normalization
#: (see fixture_likelihood_score) — analytically derived, pending empirical
#: tuning against real gallery photos.
_CC_HALF_SATURATION = 400.0
#: Half-saturation constant for texture_score's x/(x+k) normalization. Real
#: photo crops score in the thousands, so this only suppresses near-blank
#: tiles — which is its whole job (see fixture_likelihood_score).
_TEXTURE_HALF_SATURATION = 50.0
#: Share of fixture evidence carried by color separation rather than
#: non-periodicity. Color is weighted higher because it is the less ambiguous
#: signal; this also caps how high a white-on-white crop can score.
_COLOR_EVIDENCE_WEIGHT = 0.7
#: Fraction of the periodicity disk around DC excluded from
#: periodicity_score's energy-concentration measurement.
_DC_RADIUS_FRAC = 0.08
#: Number of strongest frequency bins summed for periodicity_score.
_PERIODICITY_TOP_K = 5


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


def color_contrast_score(tile: Image.Image) -> float:
    """Otsu-style between-class variance over the tile's L* channel.

    High score = the crop splits cleanly into two large, well-separated
    brightness classes (e.g. a dark object on a light background). Low
    score = uniform brightness (white-on-white) or a distribution dominated
    by a thin minority class (grout lines on a majority-tile background),
    since the class-weight term stays small whenever one class covers only
    a small fraction of pixels.
    """
    arr = np.asarray(tile.convert("RGB"), dtype=np.uint8)
    L = _srgb_to_lab(arr)[..., 0]
    L_flat = L.ravel()
    if L_flat.size == 0 or L_flat.max() == L_flat.min():
        return 0.0
    try:
        t = threshold_otsu(L_flat)
    except ValueError:
        return 0.0
    below = L_flat <= t
    n_below, n_total = int(below.sum()), L_flat.size
    if n_below == 0 or n_below == n_total:
        return 0.0
    w = n_below / n_total
    delta = float(L_flat[below].mean() - L_flat[~below].mean())
    return w * (1 - w) * delta**2


def periodicity_score(
    tile: Image.Image,
    *,
    dc_radius_frac: float = _DC_RADIUS_FRAC,
    top_k: int = _PERIODICITY_TOP_K,
) -> float:
    """FFT-based measure of regular periodic structure (e.g. a grout grid).

    High score = energy outside the DC region is concentrated into a few
    sharp frequency peaks (a regular repeating pattern). Low score = energy
    outside DC is spread smoothly across many frequencies (no sub-pattern,
    e.g. a smooth curved fixture surface) or the tile is too small to carry
    a meaningful spectrum. Bounded in [0, 1].

    Evaluated against AGENTS.md §5 (Package Fit & Upstreaming Agent): no
    existing-package equivalent found, and this is a tuned, application-
    specific heuristic rather than a general primitive — kept local rather
    than proposed upstream to scikit-image.
    """
    arr = np.asarray(tile.convert("L"), dtype=np.float32)
    h, w = arr.shape
    if h < 8 or w < 8:
        return 0.0

    win = window("hann", arr.shape)
    arr_w = (arr - arr.mean()) * win
    mag = np.abs(np.fft.fftshift(np.fft.fft2(arr_w)))

    cy, cx = h // 2, w // 2
    radius = dc_radius_frac * min(h, w)
    yy, xx = np.ogrid[:h, :w]
    outside_dc = (yy - cy) ** 2 + (xx - cx) ** 2 > radius**2

    energy = mag[outside_dc]
    if energy.size == 0:
        return 0.0
    total_energy = float(energy.sum())
    if total_energy <= 1e-8:
        return 0.0
    k = min(top_k, energy.size)
    top_k_sum = float(np.partition(energy, -k)[-k:].sum())
    return top_k_sum / total_energy


def fixture_likelihood_score(
    texture: float,
    color_contrast: float,
    periodicity: float,
    *,
    color_contrast_norm: float = _CC_HALF_SATURATION,
    texture_norm: float = _TEXTURE_HALF_SATURATION,
    color_weight: float = _COLOR_EVIDENCE_WEIGHT,
) -> float:
    """Combine texture/color-contrast/periodicity into one 0..1 score.

    Higher = more likely this crop shows "the fixture" rather than "the
    background behind it".

    Two independent pieces of evidence are blended continuously — there is no
    threshold at which one takes over, so the score has no discontinuity:

    * **color separation** — the crop splits into two distinct brightness
      regions, e.g. a dark fixture against a light wall.
    * **non-periodicity** — the crop lacks a repeating grid, so it is less
      likely to be a tiled wall. This only discriminates when the background
      actually *is* patterned.

    ``color_weight`` favours color because it is the less ambiguous signal.

    The blend is then scaled by ``presence`` — how much is in the crop at all —
    so a blank or near-uniform tile scores near zero rather than reading as
    "smooth, therefore a fixture". Real photo crops saturate ``presence``, so
    it only bites on empty ones.

    One consequence worth knowing: because color carries ``color_weight`` of
    the evidence, a white-fixture-on-white-wall crop (where color separation is
    ~0) tops out near ``1 - color_weight``. The score is therefore
    confidence-weighted — weak-evidence fixtures rank below strong-evidence
    ones by construction, which is intended for ranking but means the number
    is not an absolute probability.

    The keyword constants are half-saturation points for the ``x / (x + k)``
    normalizations; all three are first-guess values pending empirical tuning.
    """
    presence = texture / (texture + texture_norm)
    color_separation = color_contrast / (color_contrast + color_contrast_norm)
    non_periodicity = 1.0 - float(np.clip(periodicity, 0.0, 1.0))
    evidence = color_weight * color_separation + (1.0 - color_weight) * non_periodicity
    return float(np.clip(presence * evidence, 0.0, 1.0))


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

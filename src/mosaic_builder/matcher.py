from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
from PIL import Image

from .features import descriptor_mean_lab
from .tiler import make_tile


@dataclass(frozen=True)
class Patch:
    x: int
    y: int
    img: Image.Image
    desc: np.ndarray


@dataclass(frozen=True)
class Match:
    x: int
    y: int
    tile_id: str


def grid_patches(ref: Image.Image, tile_side: int, stride: int) -> Iterator[Patch]:
    ref = ref.convert("RGB")
    W, H = ref.size
    for y in range(0, H - tile_side + 1, stride):
        for x in range(0, W - tile_side + 1, stride):
            crop = ref.crop((x, y, x + tile_side, y + tile_side))
            tile = make_tile(crop, tile_side)
            desc = descriptor_mean_lab(tile)
            yield Patch(x=x, y=y, img=tile, desc=desc)


def _violates_spacing(
    grid: dict[tuple[int, int], str], gx: int, gy: int, tile_id: str, min_d: int
) -> bool:
    """Check Manhattan neighborhood within min_d for same tile_id."""
    if min_d <= 0:
        return False
    for dy in range(-min_d, min_d + 1):
        rem = min_d - abs(dy)
        for dx in range(-rem, rem + 1):
            if dx == 0 and dy == 0:
                continue
            if grid.get((gx + dx, gy + dy)) == tile_id:
                return True
    return False


def greedy_match(ref, idx, tile_side, grain=1.0) -> list[Match]:
    """
    Select and place tiles over a grid on the reference image.

    Grain semantics (grid stride + offset):
      • If grain >= 1.0 (coarse):   stride = tile_side, offset = tile_side // 2
        - This purposely *misaligns* the grid by half a tile, which is useful to
          surface and measure boundary fidelity (e.g., color edges not following
          the grid).
      • If 0 < grain < 1.0 (fine):  stride = int(round(tile_side * grain)), offset = 0
        - This aligns the grid to pixel 0 and increases placement density for
          finer sampling of boundaries.

    For each grid point (x, y), we take a tile-sized patch from `ref`, compute its
    LAB mean descriptor, query the KD index, and paste the winning tile at (x, y).
    When grain < 1.0, placements overlap (denser grid). Renderer uses "last write
    wins", which sharpens edges in practice for this use case.

    Args:
        ref (PIL.Image.Image): Reference image to match against.
        idx: KDIndex-like object with .query(vec) -> (distance, label) or similar.
             Label is normalized to a plain str to index into `tile_images`.
        tile_side (int): Tile size used for both matching patches and rendering.
        grain (float): Grid density/offset control (see semantics above).

    Returns:
        list[Match]: Each Match has .x, .y (paste position), and .tile_id (str key).

    Notes:
        • If you need deterministic control, consider future params like `stride`
          and `offset` to override `grain`.
        • For performance, be mindful that small grain (<1) increases descriptor
          computations and index queries roughly by 1/grain^2.
    """

    # Normalize a string label out of various KDIndex.query() shapes
    def _label_from_query(qres):
        try:
            a, b = qres
        except Exception:
            a, b = qres, None

        def _first_scalar(x):
            if hasattr(x, "item"):
                try:
                    return x.item()
                except Exception:
                    pass
            if isinstance(x, list | tuple | set):
                try:
                    return next(iter(x))
                except Exception:
                    return x
            if hasattr(x, "__getitem__"):
                try:
                    return x[0]
                except Exception:
                    pass
            return x

        def _to_str_label(x):
            x = _first_scalar(x)
            if isinstance(x, bytes | bytearray):
                try:
                    x = x.decode()
                except Exception:
                    pass
            if isinstance(x, list | tuple | set):
                try:
                    x = next(iter(x))
                except Exception:
                    pass
            if hasattr(x, "item"):
                try:
                    x = x.item()
                except Exception:
                    pass
            return x

        a, b = _to_str_label(a), _to_str_label(b)
        if isinstance(a, str):
            return a
        if isinstance(b, str):
            return b
        if a is not None and not isinstance(a, float | int):
            s = str(a)
            if s.startswith("['") and s.endswith("']"):
                return s[2:-2]
            if s.startswith('["') and s.endswith('"]'):
                return s[2:-2]
            return s
        if b is not None and not isinstance(b, float | int):
            s = str(b)
            if s.startswith("['") and s.endswith("']"):
                return s[2:-2]
            if s.startswith('["') and s.endswith('"]'):
                return s[2:-2]
            return s
        return str(b if b is not None else a)

    w, h = ref.size
    results: list[Match] = []

    # Clamp grain
    if grain <= 0:
        grain = 1.0

    # Derive stride and offset from grain
    if grain >= 1.0:
        stride = tile_side
        offset = tile_side // 2  # misalign coarse grid to create boundary errors
    else:
        stride = max(1, int(round(tile_side * grain)))
        offset = 0  # align fine grid to pixel zero

    # Iterate over grid positions
    # We allow positions where the patch spills over; crop will clip to image bounds.
    for y in range(offset, h, stride):
        for x in range(offset, w, stride):
            x2 = min(x + tile_side, w)
            y2 = min(y + tile_side, h)
            if x >= w or y >= h:
                continue
            if x2 <= x or y2 <= y:
                continue

            patch = ref.crop((x, y, x2, y2))
            vec = descriptor_mean_lab(patch)
            label = _label_from_query(idx.query(vec))
            label = label if isinstance(label, str) else str(label)
            results.append(Match(x, y, label))

    return results

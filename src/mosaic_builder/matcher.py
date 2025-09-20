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
    dist: float


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


def greedy_match(
    ref: Image.Image,
    index,
    tile_side: int = 24,
    *,
    grain: float = 1.0,
    max_reuse: int = 9999,
    min_repeat_distance: int = 0,
) -> list[Match]:
    """
    grain -> stride control.
    min_repeat_distance: Manhattan radius in patch units; 1 means no same tile
                         adjacent (up/down/left/right).
    """
    stride = max(1, int(round(tile_side * grain)))

    reuse_count: dict[str, int] = {}
    chosen: list[Match] = []
    # Track chosen tiles on the patch grid
    chosen_grid: dict[tuple[int, int], str] = {}

    for p in grid_patches(ref, tile_side, stride):
        gx, gy = p.x // stride, p.y // stride
        d, ids = index.query(p.desc, k=8)

        # candidates sorted by distance; apply reuse + spacing
        selected_id = None
        selected_dist = None
        for dist, cand_id in zip(d[0], ids, strict=False):
            if reuse_count.get(cand_id, 0) >= max_reuse:
                continue
            if _violates_spacing(chosen_grid, gx, gy, cand_id, min_repeat_distance):
                continue
            selected_id, selected_dist = cand_id, float(dist)
            break

        # fallback: allow best even if spacing/reuse would exclude (keeps progress)
        if selected_id is None:
            selected_id, selected_dist = ids[0], float(d[0][0])

        reuse_count[selected_id] = reuse_count.get(selected_id, 0) + 1
        chosen.append(Match(x=p.x, y=p.y, tile_id=selected_id, dist=selected_dist))
        chosen_grid[(gx, gy)] = selected_id

    return chosen

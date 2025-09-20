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
    grain: user-friendly sampling control (maps to stride)
      - 1.0 -> stride == tile_side (coarse; current default)
      - 0.5 -> stride == tile_side//2 (overlap; finer)
      - >1.0 -> stride > tile_side (skips; more impressionistic)
    """
    stride = max(1, int(round(tile_side * grain)))

    reuse_count: dict[str, int] = {}
    chosen: list[Match] = []
    for p in grid_patches(ref, tile_side, stride):
        d, ids = index.query(p.desc, k=5)
        cand = [
            (dist, id_)
            for dist, id_ in zip(d[0], ids, strict=False)
            if reuse_count.get(id_, 0) < max_reuse
        ]
        dist, id_ = cand[0] if cand else (d[0][0], ids[0])
        reuse_count[id_] = reuse_count.get(id_, 0) + 1
        chosen.append(Match(x=p.x, y=p.y, tile_id=id_, dist=float(dist)))
    return chosen

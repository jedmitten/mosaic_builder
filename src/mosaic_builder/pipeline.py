from pathlib import Path

from PIL import Image

from .features import descriptor_mean_lab
from .indexer import KDIndex
from .matcher import greedy_match
from .renderer import render_mosaic
from .tiler import make_tile


def quick(
    ref_path: str,
    tiles_dir: str,
    out_path: str,
    tile_side: int = 24,
    *,
    grain: float = 1.0,
):
    ref = Image.open(ref_path)
    tiles = {}
    for p in Path(tiles_dir).iterdir():
        if p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        try:
            tiles[p.stem] = make_tile(Image.open(p), side=tile_side)
        except Exception:
            continue
    idx = KDIndex(3)
    for k, im in tiles.items():
        idx.add(k, descriptor_mean_lab(im))
    idx.build()
    matches = greedy_match(ref, idx, tile_side=tile_side, grain=grain)
    out = render_mosaic(matches, tiles, ref.size, tile_side)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path)

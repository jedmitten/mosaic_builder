from collections import OrderedDict

from mosaic_builder.features import descriptor_mean_lab
from mosaic_builder.indexer import KDIndex
from mosaic_builder.matcher import greedy_match
from mosaic_builder.renderer import render_mosaic
from mosaic_builder.tiler import make_tile
from tests.utils import solid
from tests.vis import side_by_side


def _index_from_tiles(tiles):
    idx = KDIndex(dim=3)
    for name, im in tiles.items():
        idx.add(name, descriptor_mean_lab(im))
    idx.build()
    return idx


def _has_adjacent_repeats(matches, stride):
    # build grid keyed by (col,row)
    grid = {}
    for m in matches:
        gx, gy = m.x // stride, m.y // stride
        grid[(gx, gy)] = m.tile_id
    # check 4-neighborhood adjacency
    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    for (x, y), tid in grid.items():
        for dx, dy in dirs:
            nb = (x + dx, y + dy)
            if nb in grid and grid[nb] == tid:
                return True
    return False


def test_min_repeat_distance_avoids_adjacent_dupes(save_artifact):
    # two similar red-ish tiles so both are viable choices
    tiles = OrderedDict()
    tiles["redA"] = make_tile(solid(20, 20, (255, 0, 0)), side=12)
    tiles["redB"] = make_tile(solid(20, 20, (255, 32, 32)), side=12)
    idx = _index_from_tiles(tiles)

    # reference 24x24 solid red -> 2x2 patch grid with tile_side=12
    from PIL import Image

    ref = Image.new("RGB", (24, 24), (255, 0, 0))

    # Baseline: allow repeats -> adjacent duplicates are allowed
    matches_free = greedy_match(
        ref, idx, tile_side=12, grain=1.0, max_reuse=99, min_repeat_distance=0
    )
    assert _has_adjacent_repeats(matches_free, stride=12) is True

    # With min_repeat_distance=1 -> no same tile touches its 4-neighbors
    matches_div = greedy_match(
        ref, idx, tile_side=12, grain=1.0, max_reuse=99, min_repeat_distance=1
    )
    assert _has_adjacent_repeats(matches_div, stride=12) is False

    out_free = render_mosaic(matches_free, tiles, (24, 24), 12)
    out_div = render_mosaic(matches_div, tiles, (24, 24), 12)
    panel = side_by_side([("free", out_free), ("min_d=1", out_div)])
    save_artifact(panel, "diversity_adjacent_demo")

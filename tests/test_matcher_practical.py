from collections import OrderedDict

from mosaic_builder.features import descriptor_mean_lab
from mosaic_builder.indexer import KDIndex
from mosaic_builder.matcher import greedy_match
from mosaic_builder.tiler import make_tile
from tests.utils import solid


def _index_from_tiles(tiles):
    idx = KDIndex(dim=3)
    for name, im in tiles.items():
        idx.add(name, descriptor_mean_lab(im))
    idx.build()
    return idx


def test_greedy_prefers_color_distance():
    tiles = OrderedDict()
    tiles["red"] = make_tile(solid(20, 20, (255, 0, 0)), side=12)
    tiles["blue"] = make_tile(solid(20, 20, (0, 0, 255)), side=12)
    idx = _index_from_tiles(tiles)
    ref = solid(24, 24, (255, 0, 0))
    matches = greedy_match(ref, idx, tile_side=12, grain=1.0, max_reuse=99)
    chosen = {m.tile_id for m in matches}
    assert chosen == {"red"}

from collections import OrderedDict

from mosaic_builder.features import descriptor_mean_lab
from mosaic_builder.indexer import KDIndex
from mosaic_builder.matcher import greedy_match
from mosaic_builder.renderer import render_mosaic
from mosaic_builder.tiler import make_tile
from tests.utils import delta_e_mean, solid
from tests.vis import side_by_side


def test_render_visually_matches_reference_mean_color(
    save_artifact,
):
    tiles = OrderedDict()
    tiles["red"] = make_tile(solid(16, 16, (255, 0, 0)), side=12)
    tiles["blue"] = make_tile(solid(16, 16, (0, 0, 255)), side=12)

    idx = KDIndex(3)
    for k, im in tiles.items():
        idx.add(k, descriptor_mean_lab(im))
    idx.build()

    ref = solid(24, 24, (255, 0, 0))
    matches = greedy_match(ref, idx, tile_side=12, grain=1.0)
    out = render_mosaic(matches, tiles, canvas_size=ref.size, tile_side=12)
    # Visuals
    panel = side_by_side([("ref", ref), ("out", out)])
    save_artifact(panel, "renderer_ref_vs_out")
    assert delta_e_mean(ref, out) < 2.5

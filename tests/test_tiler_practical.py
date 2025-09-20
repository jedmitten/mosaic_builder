import numpy as np
from PIL import Image

from mosaic_builder.tiler import make_tile


def test_tiler_square_resize_and_idempotent():
    src = Image.fromarray(np.random.default_rng(0).integers(0, 255, (40, 60, 3), np.uint8), "RGB")
    t1 = make_tile(src, side=24)
    t2 = make_tile(t1, side=24)
    assert t1.size == (24, 24) and t2.size == (24, 24)

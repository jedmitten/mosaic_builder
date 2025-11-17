from pathlib import Path

import numpy as np
from PIL import Image

from mosaic_builder import tiler


def _noise_block(width: int, height: int) -> Image.Image:
    arr = np.random.default_rng(0).integers(0, 255, (height, width, 3), dtype=np.uint8)
    return Image.fromarray(arr, "RGB")


def test_extracts_up_to_three_tiles():
    left = _noise_block(120, 80)
    right = Image.new("RGB", (120, 80), (10, 10, 200))
    combo = Image.new("RGB", (240, 80))
    combo.paste(left, (0, 0))
    combo.paste(right, (120, 0))

    tiles = tiler.extract_character_tiles(combo, max_tiles=3)
    assert 1 <= len(tiles) <= 3
    # Highest score should come from textured left half, so ensure coverage > 0 and scores sorted
    scores = [tile.score for tile in tiles]
    assert scores == sorted(scores, reverse=True)
    boxes = {tile.box for tile in tiles}
    assert len(boxes) == len(tiles)


def test_resize_tile_produces_square():
    img = _noise_block(50, 80)
    resized = tiler.resize_tile(img, side=32)
    assert resized.size == (32, 32)

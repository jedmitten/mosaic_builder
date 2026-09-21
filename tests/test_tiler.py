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


def test_mean_lab_known_colors():
    # Pure white: L≈100, a≈0, b≈0
    white = Image.new("RGB", (10, 10), (255, 255, 255))
    L, a, b = tiler.mean_lab(white)
    assert 95 < L <= 100, f"White L should be ~100, got {L}"
    assert abs(a) < 5, f"White a should be ~0, got {a}"
    assert abs(b) < 5, f"White b should be ~0, got {b}"

    # Pure black: L≈0, a≈0, b≈0
    black = Image.new("RGB", (10, 10), (0, 0, 0))
    L, a, b = tiler.mean_lab(black)
    assert L < 5, f"Black L should be ~0, got {L}"

    # Red: L moderate, a positive (red-green axis)
    red = Image.new("RGB", (10, 10), (255, 0, 0))
    L, a, b = tiler.mean_lab(red)
    assert a > 20, f"Red a should be strongly positive, got {a}"


def test_delta_e_identical():
    lab = (50.0, 10.0, -5.0)
    assert tiler.delta_e(lab, lab) == 0.0


def test_delta_e_known_distance():
    lab1 = (50.0, 0.0, 0.0)
    lab2 = (50.0, 3.0, 4.0)
    # sqrt(0 + 9 + 16) = 5.0
    assert abs(tiler.delta_e(lab1, lab2) - 5.0) < 1e-6

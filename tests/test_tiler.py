from itertools import pairwise

import numpy as np
from PIL import Image

from mosaic_builder import tiler


def _noise_block(width: int, height: int) -> Image.Image:
    arr = np.random.default_rng(0).integers(0, 255, (height, width, 3), dtype=np.uint8)
    return Image.fromarray(arr, "RGB")


def _checkerboard(side: int, cell: int, lo: int = 40, hi: int = 220) -> Image.Image:
    """Grid-line-like periodic pattern: alternating light/dark square cells."""
    idx = np.arange(side)
    cell_idx = (idx // cell) % 2
    pattern = np.where(cell_idx[:, None] ^ cell_idx[None, :], hi, lo).astype(np.uint8)
    arr = np.stack([pattern] * 3, axis=-1)
    return Image.fromarray(arr, "RGB")


def _grout_grid(side: int, cell: int, line_width: int = 2, bg: int = 235, line: int = 90) -> Image.Image:
    """Thin dark grid lines on a bright majority background -- the 'tile wall' case."""
    arr = np.full((side, side), bg, dtype=np.uint8)
    for start in range(0, side, cell):
        arr[start : start + line_width, :] = line
        arr[:, start : start + line_width] = line
    return Image.fromarray(np.stack([arr] * 3, axis=-1), "RGB")


def _solid_blob_on_background(side: int, blob_frac: float = 0.4, bg: int = 235, fg: int = 25) -> Image.Image:
    """A large solid dark circular blob on a light background -- the 'black urinal' case."""
    arr = np.full((side, side), bg, dtype=np.uint8)
    yy, xx = np.ogrid[:side, :side]
    cy = cx = side / 2
    r = side * (blob_frac**0.5) / 2
    mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= r**2
    arr[mask] = fg
    return Image.fromarray(np.stack([arr] * 3, axis=-1), "RGB")


def _near_white_noise(side: int, base: int = 250, noise_amp: int = 4) -> Image.Image:
    """Uniform near-white region with tiny noise -- the 'white urinal near white wall' case."""
    rng = np.random.default_rng(1)
    noise = rng.integers(-noise_amp, noise_amp + 1, size=(side, side))
    arr = np.clip(base + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(np.stack([arr] * 3, axis=-1), "RGB")


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


def test_periodicity_score_high_for_checkerboard_low_for_noise():
    checker = tiler.periodicity_score(_checkerboard(64, 8))
    noise = tiler.periodicity_score(_near_white_noise(64))
    blob = tiler.periodicity_score(_solid_blob_on_background(64))
    assert checker > noise
    assert checker > blob


def test_periodicity_score_high_for_grout_grid():
    grout = tiler.periodicity_score(_grout_grid(64, 16))
    blob = tiler.periodicity_score(_solid_blob_on_background(64))
    noise = tiler.periodicity_score(_near_white_noise(64))
    assert grout > blob
    assert grout > noise


def test_color_contrast_score_high_for_solid_blob_low_for_grout_and_noise():
    blob = tiler.color_contrast_score(_solid_blob_on_background(64, blob_frac=0.4))
    grout = tiler.color_contrast_score(_grout_grid(64, 16, line_width=2))
    noise = tiler.color_contrast_score(_near_white_noise(64))
    assert blob > grout
    assert blob > noise


def test_color_contrast_score_low_for_uniform_white():
    noise = tiler.color_contrast_score(_near_white_noise(64, noise_amp=2))
    assert noise < 50.0


def test_fixture_likelihood_score_contrast_dominates_when_high():
    """Strong colour separation outweighs a wall-like periodicity reading."""
    score = tiler.fixture_likelihood_score(texture=3000.0, color_contrast=2000.0, periodicity=0.9)
    assert score > 0.5


def test_fixture_likelihood_score_falls_back_to_non_periodicity_when_contrast_low():
    low_periodicity = tiler.fixture_likelihood_score(texture=3000.0, color_contrast=10.0, periodicity=0.1)
    high_periodicity = tiler.fixture_likelihood_score(texture=3000.0, color_contrast=10.0, periodicity=0.9)
    assert low_periodicity > high_periodicity


def test_fixture_likelihood_score_blank_tile_scores_near_zero():
    """A featureless tile has no evidence either way, so it must not rank high.

    Guards the presence gate: before it existed, "no periodic pattern" alone
    scored a blank tile at 0.7, outranking genuine moderate-contrast objects.
    """
    blank = tiler.fixture_likelihood_score(texture=0.0, color_contrast=0.0, periodicity=0.0)
    real_object = tiler.fixture_likelihood_score(texture=3000.0, color_contrast=300.0, periodicity=0.1)
    assert blank < 0.05
    assert blank < real_object


def test_fixture_likelihood_score_is_continuous_in_color_contrast():
    """No threshold at which colour abruptly takes over the score.

    Guards against reintroducing the gated two-branch form, whose two halves
    sat on different scales and jumped at the gate.
    """
    scores = [
        tiler.fixture_likelihood_score(texture=3000.0, color_contrast=cc, periodicity=0.5)
        for cc in range(0, 1000, 10)
    ]
    steps = [b - a for a, b in pairwise(scores)]
    assert all(step > 0 for step in steps), "should rise monotonically with colour contrast"
    assert max(steps) < 0.02, f"largest single step {max(steps):.3f} looks like a discontinuity"


def test_fixture_likelihood_score_end_to_end_ordering_on_synthetic_tiles():
    def _fixture_score(tile: Image.Image) -> float:
        texture = tiler.texture_score(tile)
        cc = tiler.color_contrast_score(tile)
        per = tiler.periodicity_score(tile)
        return tiler.fixture_likelihood_score(texture, cc, per)

    blob_score = _fixture_score(_solid_blob_on_background(64))
    grout_score = _fixture_score(_grout_grid(64, 16))
    assert blob_score > grout_score


def test_color_contrast_score_degenerate_tile_returns_zero():
    tile = Image.new("RGB", (1, 1), (128, 128, 128))
    assert tiler.color_contrast_score(tile) == 0.0


def test_periodicity_score_small_tile_returns_zero():
    tile = Image.new("RGB", (4, 4), (128, 128, 128))
    assert tiler.periodicity_score(tile) == 0.0

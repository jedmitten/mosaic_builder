import pytest
from PIL import Image

from mosaic_builder import matcher


def test_solid_red_grid():
    img = Image.new("RGB", (64, 32), (200, 0, 0))
    grid = matcher.analyze_target(img, grain=16)
    assert grid.rows == 2
    assert grid.cols == 4
    assert len(grid.cells) == 8
    for cell in grid.cells:
        assert cell.lab[1] > 20


def test_remainder_dropped():
    img = Image.new("RGB", (70, 40), (0, 128, 255))
    grid = matcher.analyze_target(img, grain=32)
    assert grid.rows == 1
    assert grid.cols == 2
    assert len(grid.cells) == 2


def test_image_smaller_than_grain_raises():
    img = Image.new("RGB", (10, 10), (0, 0, 0))
    with pytest.raises(ValueError):
        matcher.analyze_target(img, grain=32)


def test_black_white_split():
    img = Image.new("RGB", (64, 32), (0, 0, 0))
    for x in range(32, 64):
        for y in range(32):
            img.putpixel((x, y), (255, 255, 255))
    grid = matcher.analyze_target(img, grain=32)
    assert grid.rows == 1
    assert grid.cols == 2
    cell_00 = next(c for c in grid.cells if c.row == 0 and c.col == 0)
    cell_01 = next(c for c in grid.cells if c.row == 0 and c.col == 1)
    assert cell_00.lab[0] < 5
    assert cell_01.lab[0] > 95

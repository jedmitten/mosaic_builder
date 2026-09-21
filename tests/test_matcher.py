import json

import pytest
from PIL import Image

from mosaic_builder import matcher
from mosaic_builder.duckdb_store import get_tile_lab_descriptors, open_database
from mosaic_builder.ingest import ingest_gallery
from mosaic_builder.tiler import mean_lab


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


def _descriptor(image_id: int, tile_index: int, lab: tuple[float, float, float]) -> dict:
    L, a, bb = lab
    return {
        "image_id": image_id,
        "tile_index": tile_index,
        "mean_L": L,
        "mean_a": a,
        "mean_b": 0.0,  # RGB blue, deliberately wrong as a LAB value
        "mean_bb": bb,
    }


def _grid(labs: list[tuple[float, float, float]], *, rows: int, cols: int, grain: int = 16):
    cells = [
        matcher.CellDescriptor(row=r, col=c, lab=labs[r * cols + c]) for r in range(rows) for c in range(cols)
    ]
    return matcher.TargetGrid(rows=rows, cols=cols, grain=grain, cells=cells)


RED_LAB = mean_lab(Image.new("RGB", (8, 8), (255, 0, 0)))
GREEN_LAB = mean_lab(Image.new("RGB", (8, 8), (0, 255, 0)))
BLUE_LAB = mean_lab(Image.new("RGB", (8, 8), (0, 0, 255)))


def test_match_grid_picks_nearest_tile():
    descriptors = [
        _descriptor(1, 0, RED_LAB),
        _descriptor(2, 0, GREEN_LAB),
        _descriptor(3, 0, BLUE_LAB),
    ]
    grid = _grid([RED_LAB, GREEN_LAB, BLUE_LAB, RED_LAB], rows=2, cols=2)
    result = matcher.match_grid(grid, descriptors, tile_side=64, db_path="mosaic.duckdb")

    assert result.rows == 2
    assert result.cols == 2
    assert result.tile_side == 64
    assert [m.image_id for m in result.matches] == [1, 2, 3, 1]
    assert all(m.delta_e < 1.0 for m in result.matches)


def test_match_grid_respects_max_reuse():
    red = RED_LAB
    dark_red = mean_lab(Image.new("RGB", (8, 8), (150, 0, 0)))
    orange = mean_lab(Image.new("RGB", (8, 8), (255, 140, 0)))
    descriptors = [
        _descriptor(1, 0, red),
        _descriptor(2, 0, dark_red),
        _descriptor(3, 0, orange),
    ]
    grid = _grid([red, red, red], rows=1, cols=3)
    result = matcher.match_grid(grid, descriptors, tile_side=64, db_path="db", max_reuse=1)

    used = [(m.image_id, m.tile_index) for m in result.matches]
    assert len(set(used)) == 3
    assert used[0] == (1, 0)


def test_match_grid_respects_min_repeat_dist():
    a_lab = RED_LAB
    b_lab = (RED_LAB[0] + 0.5, RED_LAB[1], RED_LAB[2])
    descriptors = [_descriptor(1, 0, a_lab), _descriptor(2, 0, b_lab)]
    grid = _grid([a_lab] * 4, rows=1, cols=4)
    result = matcher.match_grid(grid, descriptors, tile_side=64, db_path="db", min_repeat_dist=2)

    used = [(m.image_id, m.tile_index) for m in result.matches]
    for left, right in zip(used, used[1:], strict=False):
        assert left != right


def test_match_grid_falls_back_when_constraints_impossible():
    descriptors = [_descriptor(1, 0, RED_LAB)]
    grid = _grid([RED_LAB] * 4, rows=2, cols=2)
    result = matcher.match_grid(grid, descriptors, tile_side=64, db_path="db", max_reuse=1)

    assert len(result.matches) == 4
    assert all((m.image_id, m.tile_index) == (1, 0) for m in result.matches)


def test_match_grid_empty_descriptors_raises():
    grid = _grid([RED_LAB], rows=1, cols=1)
    with pytest.raises(ValueError):
        matcher.match_grid(grid, [], tile_side=64, db_path="db")


def test_match_result_json_round_trip(tmp_path):
    result = matcher.MatchResult(
        rows=2,
        cols=3,
        grain=32,
        tile_side=64,
        db_path="mosaic.duckdb",
        matches=[
            matcher.CellMatch(row=r, col=c, image_id=r + 1, tile_index=c, delta_e=1.5 * (r + c))
            for r in range(2)
            for c in range(3)
        ],
    )
    path = tmp_path / "match.json"
    matcher.save_match_result(result, path)

    payload = json.loads(path.read_text())
    assert payload["tile_side"] == 64
    assert payload["matches"][0].keys() == {"row", "col", "image_id", "tile_index", "delta_e"}

    assert matcher.load_match_result(path) == result


def test_run_match_end_to_end(tmp_path):
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    Image.new("RGB", (120, 90), (220, 20, 20)).save(gallery / "red.png")
    Image.new("RGB", (120, 90), (20, 20, 220)).save(gallery / "blue.png")

    db_path = tmp_path / "tiles.duckdb"
    ingest_gallery(gallery, db_path, tile_side=16, show_progress=False)

    target = tmp_path / "target.png"
    Image.new("RGB", (64, 64), (220, 20, 20)).save(target)

    result = matcher.run_match(target, db_path, grain=16, show_progress=False)

    assert result.rows == 4
    assert result.cols == 4
    assert result.tile_side == 16
    assert len(result.matches) == 16
    assert result.db_path == str(db_path)

    conn = open_database(db_path)
    try:
        known = {(d["image_id"], d["tile_index"]) for d in get_tile_lab_descriptors(conn, tile_side=16)}
    finally:
        conn.close()
    assert {(m.image_id, m.tile_index) for m in result.matches} <= known

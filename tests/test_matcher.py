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


def test_match_grid_diversity_zero_is_pure_nearest_match():
    """The dial at 0 must reproduce plain nearest-colour matching exactly."""
    red = RED_LAB
    dark_red = mean_lab(Image.new("RGB", (8, 8), (150, 0, 0)))
    descriptors = [_descriptor(1, 0, red), _descriptor(2, 0, dark_red)]
    grid = _grid([red, red, red], rows=1, cols=3)
    result = matcher.match_grid(grid, descriptors, tile_side=64, db_path="db", diversity=0.0)

    used = [(m.image_id, m.tile_index) for m in result.matches]
    assert used == [(1, 0)] * 3


def test_match_grid_diversity_spreads_tiles():
    """Among comparable alternatives, the dial spreads usage across them.

    Uses near-identical tiles because that is the realistic case: this
    gallery's mean nearest-neighbour distance is around 1 Delta-E.
    """
    near = [
        RED_LAB,
        (RED_LAB[0] + 1.0, RED_LAB[1], RED_LAB[2]),
        (RED_LAB[0] + 2.0, RED_LAB[1], RED_LAB[2]),
    ]
    descriptors = [_descriptor(i + 1, 0, lab) for i, lab in enumerate(near)]
    grid = _grid([RED_LAB] * 3, rows=1, cols=3)
    result = matcher.match_grid(grid, descriptors, tile_side=64, db_path="db", diversity=10.0)

    used = [(m.image_id, m.tile_index) for m in result.matches]
    assert len(set(used)) == 3
    assert used[0] == (1, 0), "the first cell has no reuse history, so it takes the best match"


def test_match_grid_diversity_will_not_swap_to_a_far_worse_tile():
    """Diversity is a preference, not a mandate.

    A blue tile is ~40 Delta-E from red — far past the point where a mismatch
    reads as wrong — so even a maxed dial keeps reusing the red tile rather
    than vandalising the mosaic for the sake of variety.
    """
    blue = mean_lab(Image.new("RGB", (8, 8), (0, 0, 255)))
    descriptors = [_descriptor(1, 0, RED_LAB), _descriptor(2, 0, blue)]
    grid = _grid([RED_LAB] * 3, rows=1, cols=3)
    result = matcher.match_grid(grid, descriptors, tile_side=64, db_path="db", diversity=10.0)

    assert all((m.image_id, m.tile_index) == (1, 0) for m in result.matches)


def test_match_grid_diversity_trades_fidelity_for_variety_monotonically():
    """Turning the dial up must not reduce variety or improve mean delta-E."""
    labs = [RED_LAB, mean_lab(Image.new("RGB", (8, 8), (200, 20, 20)))]
    descriptors = [_descriptor(i, 0, lab) for i, lab in enumerate(labs)]
    grid = _grid([RED_LAB] * 16, rows=4, cols=4)

    previous_distinct, previous_mean = 0, -1.0
    for dial in (0.0, 2.0, 5.0, 10.0):
        result = matcher.match_grid(grid, descriptors, tile_side=64, db_path="db", diversity=dial)
        distinct = len({(m.image_id, m.tile_index) for m in result.matches})
        mean_delta_e = sum(m.delta_e for m in result.matches) / len(result.matches)
        assert distinct >= previous_distinct
        assert mean_delta_e >= previous_mean
        previous_distinct, previous_mean = distinct, mean_delta_e


def test_match_grid_diversity_does_not_degrade_when_tiles_are_scarce():
    """Reuse pressure must never force in a wildly wrong tile.

    With far fewer tiles than cells every tile has to repeat. Charging for
    that unavoidable reuse from the first repeat made the penalty grow without
    bound until it swamped colour distance, and the matcher started reaching
    for terrible tiles purely to avoid repeating. Penalties are measured
    against each tile's fair share (cells / tiles) so that cannot happen.
    """
    good = RED_LAB
    acceptable = (RED_LAB[0] + 4.0, RED_LAB[1], RED_LAB[2])
    terrible = mean_lab(Image.new("RGB", (8, 8), (0, 0, 255)))
    descriptors = [
        _descriptor(1, 0, good),
        _descriptor(2, 0, acceptable),
        _descriptor(3, 0, terrible),
    ]
    grid = _grid([RED_LAB] * 100, rows=10, cols=10)
    result = matcher.match_grid(grid, descriptors, tile_side=64, db_path="db", diversity=10.0)

    terrible_uses = sum(1 for m in result.matches if m.image_id == 3)
    assert terrible_uses == 0, "a ~40 delta-E tile must never be forced in by reuse pressure"


def test_match_grid_single_tile_still_fills_every_cell():
    """With one tile there is no variety to find, but every cell must be filled."""
    descriptors = [_descriptor(1, 0, RED_LAB)]
    grid = _grid([RED_LAB] * 4, rows=2, cols=2)
    result = matcher.match_grid(grid, descriptors, tile_side=64, db_path="db", diversity=10.0)

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

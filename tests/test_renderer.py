import io
import tempfile
from pathlib import Path

import duckdb
import pytest
from conftest import make_tile
from PIL import Image

from mosaic_builder import renderer
from mosaic_builder.duckdb_store import ensure_schema, open_database, upsert_image, upsert_tiles
from mosaic_builder.matcher import CellMatch, MatchResult, save_match_result

RED = (255, 0, 0)
BLUE = (0, 0, 255)
GREEN = (0, 255, 0)


def _png_bytes(color: tuple[int, int, int], side: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (side, side), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _tile(
    *, tile_index: int, color: tuple[int, int, int], tile_side: int, png_side: int | None = None
) -> dict:
    return make_tile(
        tile_side=tile_side,
        tile_index=tile_index,
        crop_box=f"0,0,{tile_side},{tile_side}",
        coverage=1.0,
        mean_r=float(color[0]),
        mean_g=float(color[1]),
        mean_b=float(color[2]),
        mean_L=50.0,
        mean_a=0.0,
        mean_bb=0.0,
        tile_png=_png_bytes(color, png_side or tile_side),
    )


def _make_db(tmp: str, tiles: list[dict], *, name: str = "tiles.duckdb") -> duckdb.DuckDBPyConnection:
    conn = open_database(Path(tmp) / name)
    ensure_schema(conn)
    image_id = upsert_image(conn, str(Path(tmp) / "source.png"), 64, 64)
    upsert_tiles(conn, image_id, tiles)
    return conn


def _image_id(conn: duckdb.DuckDBPyConnection) -> int:
    return int(conn.execute("SELECT image_id FROM images").fetchone()[0])


def test_assemble_mosaic_places_tiles_correctly():
    with tempfile.TemporaryDirectory() as tmp:
        conn = _make_db(
            tmp,
            [
                _tile(tile_index=0, color=RED, tile_side=8),
                _tile(tile_index=1, color=BLUE, tile_side=8),
            ],
        )
        try:
            image_id = _image_id(conn)
            result = MatchResult(
                rows=2,
                cols=2,
                grain=8,
                tile_side=8,
                db_path="ignored.duckdb",
                matches=[
                    CellMatch(row=0, col=0, image_id=image_id, tile_index=0, delta_e=0.0),
                    CellMatch(row=0, col=1, image_id=image_id, tile_index=1, delta_e=0.0),
                    CellMatch(row=1, col=0, image_id=image_id, tile_index=1, delta_e=0.0),
                    CellMatch(row=1, col=1, image_id=image_id, tile_index=0, delta_e=0.0),
                ],
            )
            mosaic = renderer.assemble_mosaic(result, conn)
            assert mosaic.size == (16, 16)
            assert mosaic.mode == "RGB"
            assert mosaic.getpixel((0, 0)) == RED
            assert mosaic.getpixel((15, 0)) == BLUE
            assert mosaic.getpixel((0, 15)) == BLUE
            assert mosaic.getpixel((15, 15)) == RED
        finally:
            conn.close()


def test_assemble_mosaic_non_square_grid_is_not_transposed():
    with tempfile.TemporaryDirectory() as tmp:
        conn = _make_db(
            tmp,
            [
                _tile(tile_index=0, color=RED, tile_side=8),
                _tile(tile_index=1, color=GREEN, tile_side=8),
                _tile(tile_index=2, color=BLUE, tile_side=8),
            ],
        )
        try:
            image_id = _image_id(conn)
            result = MatchResult(
                rows=1,
                cols=3,
                grain=8,
                tile_side=8,
                db_path="ignored.duckdb",
                matches=[
                    CellMatch(row=0, col=0, image_id=image_id, tile_index=0, delta_e=0.0),
                    CellMatch(row=0, col=1, image_id=image_id, tile_index=1, delta_e=0.0),
                    CellMatch(row=0, col=2, image_id=image_id, tile_index=2, delta_e=0.0),
                ],
            )
            mosaic = renderer.assemble_mosaic(result, conn)
            assert mosaic.size == (24, 8)
            assert mosaic.getpixel((0, 0)) == RED
            assert mosaic.getpixel((8, 0)) == GREEN
            assert mosaic.getpixel((16, 0)) == BLUE
        finally:
            conn.close()


def test_assemble_mosaic_resizes_wrong_sized_tile():
    with tempfile.TemporaryDirectory() as tmp:
        conn = _make_db(tmp, [_tile(tile_index=0, color=RED, tile_side=8, png_side=5)])
        try:
            image_id = _image_id(conn)
            result = MatchResult(
                rows=1,
                cols=1,
                grain=8,
                tile_side=8,
                db_path="ignored.duckdb",
                matches=[CellMatch(row=0, col=0, image_id=image_id, tile_index=0, delta_e=0.0)],
            )
            mosaic = renderer.assemble_mosaic(result, conn)
            assert mosaic.size == (8, 8)
            assert mosaic.getpixel((7, 7)) == RED
        finally:
            conn.close()


def test_assemble_mosaic_missing_tile_raises_keyerror():
    with tempfile.TemporaryDirectory() as tmp:
        conn = _make_db(tmp, [_tile(tile_index=0, color=RED, tile_side=8)])
        try:
            image_id = _image_id(conn)
            result = MatchResult(
                rows=1,
                cols=1,
                grain=8,
                tile_side=8,
                db_path="ignored.duckdb",
                matches=[CellMatch(row=0, col=0, image_id=image_id, tile_index=99, delta_e=0.0)],
            )
            with pytest.raises(KeyError) as excinfo:
                renderer.assemble_mosaic(result, conn)
            assert "99" in str(excinfo.value)
        finally:
            conn.close()


def test_blend_with_target_alpha_bounds():
    mosaic = Image.new("RGB", (16, 16), RED)
    target = Image.new("RGB", (32, 32), BLUE)

    unchanged = renderer.blend_with_target(mosaic, target, 0.0)
    assert list(unchanged.getdata()) == list(mosaic.getdata())

    full = renderer.blend_with_target(mosaic, target, 1.0)
    resized = target.convert("RGB").resize(mosaic.size, Image.Resampling.LANCZOS)
    assert list(full.getdata()) == list(resized.getdata())


def test_blend_with_target_rejects_out_of_range_alpha():
    mosaic = Image.new("RGB", (8, 8), RED)
    target = Image.new("RGB", (8, 8), BLUE)
    with pytest.raises(ValueError):
        renderer.blend_with_target(mosaic, target, 1.5)
    with pytest.raises(ValueError):
        renderer.blend_with_target(mosaic, target, -0.1)


def test_run_render_writes_png_and_requires_target_for_blend():
    with tempfile.TemporaryDirectory() as tmp:
        conn = _make_db(tmp, [_tile(tile_index=0, color=RED, tile_side=8)], name="render.duckdb")
        try:
            image_id = _image_id(conn)
        finally:
            conn.close()

        match_path = Path(tmp) / "match.json"
        out_path = Path(tmp) / "out" / "mosaic.png"
        save_match_result(
            MatchResult(
                rows=1,
                cols=2,
                grain=8,
                tile_side=8,
                db_path=str(Path(tmp) / "render.duckdb"),
                matches=[
                    CellMatch(row=0, col=0, image_id=image_id, tile_index=0, delta_e=0.0),
                    CellMatch(row=0, col=1, image_id=image_id, tile_index=0, delta_e=0.0),
                ],
            ),
            match_path,
        )

        db_path = Path(tmp) / "render.duckdb"
        written = renderer.run_render(match_path, db_path, out_path, show_progress=False)
        assert written.exists()
        with Image.open(written) as rendered:
            assert rendered.size == (16, 8)

        with pytest.raises(ValueError):
            renderer.run_render(match_path, db_path, out_path, blend=0.5, show_progress=False)

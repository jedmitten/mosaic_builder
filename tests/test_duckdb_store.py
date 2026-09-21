import tempfile
from pathlib import Path
from unittest import TestCase

import duckdb

from mosaic_builder.duckdb_store import (
    ensure_schema,
    get_all_images,
    get_all_tiles,
    get_tile_lab_descriptors,
    get_tile_png,
    get_tiles_for_image,
    normalize_db_path,
    open_database,
    upsert_image,
    upsert_tiles,
)


def _make_conn(tmp: str) -> duckdb.DuckDBPyConnection:
    db_path = Path(tmp) / "test.duckdb"
    conn = open_database(db_path)
    ensure_schema(conn)
    return conn


def _sample_tile(*, tile_index: int = 0, tile_png: bytes = b"\x89PNG") -> dict:
    """Return a minimal valid tile dict with LAB fields."""
    return {
        "tile_side": 32,
        "tile_index": tile_index,
        "crop_box": "0,0,32,32",
        "coverage": 0.5,
        "score": 1.0,
        "mean_r": 100.0,
        "mean_g": 50.0,
        "mean_b": 25.0,
        "mean_L": 45.0,
        "mean_a": 12.0,
        "mean_bb": -8.0,
        "tile_png": tile_png,
    }


class DuckDBStoreTest(TestCase):
    def test_normalize_db_path_creates_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "store.duckdb"
            normalized = normalize_db_path(path)
            self.assertEqual(normalized, path)
            self.assertTrue(path.parent.exists())

    def test_open_database_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tiles.duckdb"
            conn = open_database(db_path)
            try:
                ensure_schema(conn)
                tables = {
                    row[0]
                    for row in conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
                }
                self.assertIn("images", tables)
                self.assertIn("tiles", tables)
            finally:
                conn.close()

    def test_sequence_auto_increments(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                id1 = upsert_image(conn, "/a.png", 100, 100)
                id2 = upsert_image(conn, "/b.png", 100, 100)
                self.assertGreater(id2, id1)
            finally:
                conn.close()

    def test_upsert_image_replaces_on_same_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                upsert_image(conn, "/a.png", 100, 100)
                upsert_image(conn, "/a.png", 200, 200)
                images = get_all_images(conn)
                self.assertEqual(len(images), 1)
                self.assertEqual(images[0]["width"], 200)
            finally:
                conn.close()

    def test_cascade_delete_removes_tiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                img_id = upsert_image(conn, "/a.png", 100, 100)
                upsert_tiles(conn, img_id, [_sample_tile()])
                self.assertEqual(len(get_tiles_for_image(conn, img_id)), 1)
                new_id = upsert_image(conn, "/a.png", 200, 200)
                self.assertNotEqual(img_id, new_id)
                self.assertEqual(len(get_tiles_for_image(conn, img_id)), 0)
            finally:
                conn.close()

    def test_get_all_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                upsert_image(conn, "/a.png", 100, 100)
                upsert_image(conn, "/b.png", 200, 200)
                images = get_all_images(conn)
                self.assertEqual(len(images), 2)
                paths = {img["path"] for img in images}
                self.assertEqual(paths, {"/a.png", "/b.png"})
            finally:
                conn.close()

    def test_get_tiles_for_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                img_id = upsert_image(conn, "/a.png", 100, 100)
                upsert_tiles(
                    conn,
                    img_id,
                    [
                        _sample_tile(tile_index=0, tile_png=b"\x89PNG_TILE0"),
                        _sample_tile(tile_index=1, tile_png=b"\x89PNG_TILE1"),
                    ],
                )
                tiles = get_tiles_for_image(conn, img_id)
                self.assertEqual(len(tiles), 2)
                self.assertEqual(tiles[0]["tile_index"], 0)
                self.assertEqual(tiles[1]["tile_index"], 1)
            finally:
                conn.close()

    def test_get_tile_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                img_id = upsert_image(conn, "/a.png", 100, 100)
                png_data = b"\x89PNG_REAL_DATA"
                upsert_tiles(conn, img_id, [_sample_tile(tile_png=png_data)])
                result = get_tile_png(conn, img_id, 0)
                self.assertEqual(result, png_data)
            finally:
                conn.close()

    def test_get_tile_png_missing_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                with self.assertRaises(KeyError):
                    get_tile_png(conn, 999, 0)
            finally:
                conn.close()

    def test_get_all_tiles_limit_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                img_id = upsert_image(conn, "/a.png", 100, 100)
                upsert_tiles(conn, img_id, [_sample_tile(tile_index=i) for i in range(5)])
                all_tiles = get_all_tiles(conn)
                self.assertEqual(len(all_tiles), 5)
                limited = get_all_tiles(conn, limit=2, offset=1)
                self.assertEqual(len(limited), 2)
                self.assertEqual(limited[0]["tile_index"], 1)
            finally:
                conn.close()

    def test_lab_columns_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                img_id = upsert_image(conn, "/a.png", 100, 100)
                upsert_tiles(conn, img_id, [_sample_tile()])
                tiles = get_tiles_for_image(conn, img_id)
                self.assertEqual(len(tiles), 1)
                self.assertAlmostEqual(tiles[0]["mean_L"], 45.0, places=2)
                self.assertAlmostEqual(tiles[0]["mean_a"], 12.0, places=2)
                self.assertAlmostEqual(tiles[0]["mean_bb"], -8.0, places=2)
            finally:
                conn.close()

    def test_get_tile_lab_descriptors_no_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                img_id = upsert_image(conn, "/a.png", 100, 100)
                upsert_tiles(conn, img_id, [_sample_tile()])
                descs = get_tile_lab_descriptors(conn)
                self.assertEqual(len(descs), 1)
                self.assertIn("mean_L", descs[0])
                self.assertNotIn("tile_png", descs[0])
            finally:
                conn.close()

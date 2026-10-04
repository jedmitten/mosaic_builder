import math
import tempfile
from pathlib import Path
from unittest import TestCase

from PIL import Image

from mosaic_builder.duckdb_store import (
    ensure_schema,
    get_all_images,
    get_tiles_for_image,
    open_database,
)
from mosaic_builder.ingest import ingest_gallery
from mosaic_builder.preview import render_preview


def _solid(width: int, height: int, color: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (width, height), color)


class IngestPreviewTest(TestCase):
    def test_ingest_and_preview_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            images_dir = Path(tmp) / "gallery"
            images_dir.mkdir()
            (_solid(200, 140, (200, 30, 30))).save(images_dir / "red.png")
            (_solid(140, 200, (30, 200, 30))).save(images_dir / "green.png")

            db_path = Path(tmp) / "tiles.duckdb"
            tile_side = 32

            # Ingest returns a summary, not previews
            summary = ingest_gallery(images_dir, db_path, tile_side=tile_side, show_progress=False)
            self.assertEqual(summary.images, 2)
            self.assertGreaterEqual(summary.tiles, 2)

            # Verify DB state
            conn = open_database(db_path)
            ensure_schema(conn)
            try:
                images = get_all_images(conn)
                self.assertEqual(len(images), 2)
                for img in images:
                    tiles = get_tiles_for_image(conn, img["image_id"])
                    self.assertGreater(len(tiles), 0)
                    for tile in tiles:
                        self.assertEqual(tile["tile_side"], tile_side)
                        self.assertIsInstance(tile["tile_png"], bytes)
                        self.assertGreater(len(tile["tile_png"]), 0)
                        for key in ("score", "color_contrast", "periodicity"):
                            self.assertIsInstance(tile[key], float)
                            self.assertTrue(math.isfinite(tile[key]))
            finally:
                conn.close()

            # Preview reads from DB
            out_html = Path(tmp) / "preview.html"
            render_preview(db_path, out_html)
            self.assertTrue(out_html.exists())
            content = out_html.read_text()
            self.assertIn("<!DOCTYPE html>", content)
            self.assertIn("data:image/png;base64,", content)

    def test_ingest_is_transactional(self):
        """Re-ingesting the same gallery replaces images cleanly."""
        with tempfile.TemporaryDirectory() as tmp:
            images_dir = Path(tmp) / "gallery"
            images_dir.mkdir()
            (_solid(100, 100, (255, 0, 0))).save(images_dir / "red.png")

            db_path = Path(tmp) / "tiles.duckdb"
            ingest_gallery(images_dir, db_path, tile_side=32, show_progress=False)
            ingest_gallery(images_dir, db_path, tile_side=32, show_progress=False)

            conn = open_database(db_path)
            ensure_schema(conn)
            try:
                images = get_all_images(conn)
                self.assertEqual(len(images), 1)
            finally:
                conn.close()

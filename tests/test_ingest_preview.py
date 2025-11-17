import tempfile
from pathlib import Path
from unittest import TestCase

import duckdb
from PIL import Image

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
            previews = ingest_gallery(images_dir, db_path, tile_side=32, show_progress=False)

            self.assertEqual(len(previews), 2)
            self.assertTrue(all(preview.original_data_url.startswith("data:image/png") for preview in previews))

            conn = duckdb.connect(str(db_path))
            try:
                num_images = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
                self.assertEqual(num_images, 2)
                num_tiles = conn.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]
                self.assertGreaterEqual(num_tiles, 2)
                tile_blob = conn.execute("SELECT tile_png FROM tiles LIMIT 1").fetchone()[0]
                self.assertIsInstance(tile_blob, (bytes, bytearray))
                self.assertGreater(len(tile_blob), 0)
            finally:
                conn.close()

            out_html = Path(tmp) / "preview.html"
            render_preview(previews, out_html)
            self.assertTrue(out_html.exists())
            content = out_html.read_text()
            self.assertIn("<!DOCTYPE html>", content)

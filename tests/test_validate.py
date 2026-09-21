import json
import tempfile
from pathlib import Path
from unittest import TestCase

from mosaic_builder.duckdb_store import ensure_schema, open_database, upsert_image, upsert_tiles
from mosaic_builder.validate import gallery_report


def _make_conn(tmp: str) -> "object":
    db_path = Path(tmp) / "validate.duckdb"
    conn = open_database(db_path)
    ensure_schema(conn)
    return conn


def _tile(
    *,
    tile_index: int = 0,
    tile_side: int = 32,
    coverage: float = 0.5,
    score: float = 1.0,
    mean_r: float = 100.0,
    mean_g: float = 50.0,
    mean_b: float = 25.0,
    mean_L: float = 45.0,
    mean_a: float = 12.0,
    mean_bb: float = -8.0,
) -> dict:
    return {
        "tile_side": tile_side,
        "tile_index": tile_index,
        "crop_box": "0,0,32,32",
        "coverage": coverage,
        "score": score,
        "mean_r": mean_r,
        "mean_g": mean_g,
        "mean_b": mean_b,
        "mean_L": mean_L,
        "mean_a": mean_a,
        "mean_bb": mean_bb,
        "tile_png": b"\x89PNG",
    }


class GalleryReportTest(TestCase):
    def test_empty_database_reports_zero_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                report = gallery_report(conn)
            finally:
                conn.close()

            self.assertEqual(report["image_count"], 0)
            self.assertEqual(report["tile_count"], 0)
            self.assertEqual(report["tile_sides"], [])
            self.assertEqual(report["lab_ranges"], {"L": None, "a": None, "b": None})
            self.assertIsNone(report["mean_nearest_neighbor_delta_e"])
            self.assertEqual(report["low_texture_tiles"], [])
            self.assertEqual(sum(report["coverage_histogram"].values()), 0)

    def test_mean_nearest_neighbor_delta_e_two_tiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                image_id = upsert_image(conn, "img.png", 64, 64)
                upsert_tiles(
                    conn,
                    image_id,
                    [
                        _tile(tile_index=0, mean_L=50.0, mean_a=0.0, mean_bb=0.0),
                        _tile(tile_index=1, mean_L=50.0, mean_a=3.0, mean_bb=4.0),
                    ],
                )
                report = gallery_report(conn)
            finally:
                conn.close()

            self.assertAlmostEqual(report["mean_nearest_neighbor_delta_e"], 5.0, places=6)

    def test_lab_ranges_b_is_derived_from_mean_bb_not_mean_b(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                image_id = upsert_image(conn, "img.png", 64, 64)
                upsert_tiles(
                    conn,
                    image_id,
                    [_tile(tile_index=0, mean_b=200.0, mean_bb=-7.0)],
                )
                report = gallery_report(conn)
            finally:
                conn.close()

            self.assertEqual(report["lab_ranges"]["b"], [-7.0, -7.0])

    def test_coverage_histogram_bucket_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                image_id = upsert_image(conn, "img.png", 64, 64)
                upsert_tiles(
                    conn,
                    image_id,
                    [
                        _tile(tile_index=0, coverage=0.0),
                        _tile(tile_index=1, coverage=0.25),
                        _tile(tile_index=2, coverage=0.5),
                        _tile(tile_index=3, coverage=0.75),
                        _tile(tile_index=4, coverage=1.0),
                    ],
                )
                report = gallery_report(conn)
            finally:
                conn.close()

            hist = report["coverage_histogram"]
            buckets = list(hist.keys())
            self.assertEqual(hist[buckets[0]], 1)  # 0.0
            self.assertEqual(hist[buckets[1]], 1)  # 0.25
            self.assertEqual(hist[buckets[2]], 1)  # 0.5
            self.assertEqual(hist[buckets[3]], 2)  # 0.75 and 1.0

    def test_single_tile_database_nearest_neighbor_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                image_id = upsert_image(conn, "img.png", 64, 64)
                upsert_tiles(conn, image_id, [_tile(tile_index=0)])
                report = gallery_report(conn)
            finally:
                conn.close()

            self.assertIsNone(report["mean_nearest_neighbor_delta_e"])

    def test_report_is_json_serialisable(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_conn(tmp)
            try:
                image_id = upsert_image(conn, "img.png", 64, 64)
                upsert_tiles(
                    conn,
                    image_id,
                    [
                        _tile(tile_index=0, coverage=0.1, score=0.2, mean_L=10.0, mean_a=1.0, mean_bb=2.0),
                        _tile(tile_index=1, coverage=0.9, score=0.8, mean_L=90.0, mean_a=-1.0, mean_bb=-2.0),
                    ],
                )
                report = gallery_report(conn)
            finally:
                conn.close()

            serialised = json.dumps(report)
            self.assertIsInstance(serialised, str)

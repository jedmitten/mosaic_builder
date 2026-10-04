"""Tests for schema versioning and legacy-database detection."""

import tempfile
from pathlib import Path
from unittest import TestCase

import duckdb
from PIL import Image

from mosaic_builder.duckdb_store import (
    SCHEMA_VERSION,
    SchemaVersionError,
    ensure_schema,
    get_schema_version,
    open_database,
    stamp_schema_version,
)
from mosaic_builder.ingest import ingest_gallery

_SCHEMA_META_DDL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key VARCHAR PRIMARY KEY,
    value VARCHAR NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_LEGACY_IMAGES_DDL = """
CREATE TABLE images (
    image_id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL
);
"""

# The pre-LAB tiles table: no tile_side, no mean_L/mean_a/mean_bb.
_LEGACY_TILES_DDL = """
CREATE TABLE tiles (
    image_id INTEGER NOT NULL,
    tile_index INTEGER NOT NULL,
    crop_box TEXT NOT NULL,
    coverage REAL NOT NULL,
    score REAL NOT NULL,
    mean_r REAL NOT NULL,
    mean_g REAL NOT NULL,
    mean_b REAL NOT NULL,
    descriptor TEXT,
    tile_png BLOB NOT NULL
);
"""


def _build_legacy_db(path: Path) -> None:
    """Create a populated pre-LAB database at ``path`` and close it."""
    conn = duckdb.connect(str(path))
    try:
        conn.execute(_LEGACY_IMAGES_DDL)
        conn.execute(_LEGACY_TILES_DDL)
        conn.execute("INSERT INTO images VALUES (1, '/a.png', 100, 100)")
        conn.execute(
            "INSERT INTO tiles VALUES (1, 0, '0,0,32,32', 0.5, 1.0, 10.0, 20.0, 30.0, NULL, ?)",
            [b"\x89PNG"],
        )
    finally:
        conn.close()


class SchemaVersionTest(TestCase):
    def test_fresh_database_is_stamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = open_database(Path(tmp) / "fresh.duckdb")
            try:
                ensure_schema(conn)
                self.assertEqual(get_schema_version(conn), SCHEMA_VERSION)
            finally:
                conn.close()

    def test_ensure_schema_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = open_database(Path(tmp) / "fresh.duckdb")
            try:
                ensure_schema(conn)
                ensure_schema(conn)
                count = conn.execute("SELECT count(*) FROM schema_meta").fetchone()[0]
                self.assertEqual(count, 1)
            finally:
                conn.close()

    def test_get_schema_version_without_schema_meta_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = duckdb.connect(str(Path(tmp) / "bare.duckdb"))
            try:
                self.assertIsNone(get_schema_version(conn))
            finally:
                conn.close()

    def test_legacy_database_raises_schema_version_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.duckdb"
            _build_legacy_db(db_path)
            conn = duckdb.connect(str(db_path))
            try:
                with self.assertRaises(SchemaVersionError) as ctx:
                    ensure_schema(conn)
            finally:
                conn.close()
            message = str(ctx.exception)
            self.assertIn("delete", message.lower())
            self.assertIn("out of date", message.lower())
            self.assertNotIsInstance(ctx.exception, duckdb.BinderException)

    def test_older_version_raises_naming_both_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = open_database(Path(tmp) / "old.duckdb")
            try:
                ensure_schema(conn)
                stamp_schema_version(conn, SCHEMA_VERSION - 1)
                with self.assertRaises(SchemaVersionError) as ctx:
                    ensure_schema(conn)
            finally:
                conn.close()
            message = str(ctx.exception)
            self.assertIn(str(SCHEMA_VERSION - 1), message)
            self.assertIn(str(SCHEMA_VERSION), message)
            self.assertIn("delete", message.lower())

    def test_future_version_raises_asking_for_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = open_database(Path(tmp) / "future.duckdb")
            try:
                ensure_schema(conn)
                stamp_schema_version(conn, SCHEMA_VERSION + 1)
                with self.assertRaises(SchemaVersionError) as ctx:
                    ensure_schema(conn)
            finally:
                conn.close()
            message = str(ctx.exception)
            self.assertIn("upgrade", message.lower())
            self.assertIn(str(SCHEMA_VERSION + 1), message)

    def test_missing_column_guard_names_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = duckdb.connect(str(Path(tmp) / "partial.duckdb"))
            try:
                # Stamp the correct version first so this is not seen as legacy.
                conn.execute(_SCHEMA_META_DDL)
                stamp_schema_version(conn, SCHEMA_VERSION)
                conn.execute(
                    """
                    CREATE TABLE tiles (
                        image_id INTEGER NOT NULL,
                        tile_side INTEGER NOT NULL,
                        tile_index INTEGER NOT NULL,
                        crop_box TEXT NOT NULL,
                        coverage REAL NOT NULL,
                        score REAL NOT NULL,
                        mean_r REAL NOT NULL,
                        mean_g REAL NOT NULL,
                        mean_b REAL NOT NULL,
                        mean_a REAL NOT NULL,
                        mean_bb REAL NOT NULL,
                        tile_png BLOB NOT NULL
                    );
                    """
                )
                with self.assertRaises(SchemaVersionError) as ctx:
                    ensure_schema(conn)
            finally:
                conn.close()
            self.assertIn("mean_L", str(ctx.exception))

    def test_ingest_gallery_on_legacy_database_raises_schema_version_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            gallery = tmp_path / "gallery"
            gallery.mkdir()
            for name, colour in (("a.png", (200, 30, 30)), ("b.png", (30, 200, 30))):
                Image.new("RGB", (64, 64), colour).save(gallery / name)

            db_path = tmp_path / "legacy.duckdb"
            _build_legacy_db(db_path)

            with self.assertRaises(SchemaVersionError) as ctx:
                ingest_gallery(gallery, db_path, tile_side=32, show_progress=False)
            self.assertNotIsInstance(ctx.exception, duckdb.BinderException)
            self.assertIn("delete", str(ctx.exception).lower())

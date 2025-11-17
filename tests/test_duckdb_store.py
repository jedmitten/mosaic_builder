import tempfile
from pathlib import Path
from unittest import TestCase

import duckdb

from mosaic_builder.duckdb_store import ensure_schema, normalize_db_path, open_database


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

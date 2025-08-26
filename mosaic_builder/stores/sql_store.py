from __future__ import annotations

from pathlib import Path

import numpy as np


class SqlTileStore:
    def __init__(self, conn, engine: str):
        self.conn = conn
        self.engine = engine  # "sqlite" | "duckdb"

    def ensure_schema(self) -> None:
        cur = self.conn.cursor()
        if self.engine == "sqlite":
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                width INT NOT NULL,
                height INT NOT NULL
                );
            """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS grids (
                id INTEGER PRIMARY KEY,
                photo_id INT NOT NULL,
                tile_w INT NOT NULL,
                tile_h INT NOT NULL,
                cols INT NOT NULL,
                rows INT NOT NULL,
                UNIQUE(photo_id, tile_w, tile_h)
                );
            """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tiles (
                id INTEGER PRIMARY KEY,
                grid_id INT NOT NULL,
                x INT NOT NULL,
                y INT NOT NULL,
                l REAL NOT NULL, a REAL NOT NULL, b REAL NOT NULL
                );
            """
            )
        else:  # duckdb
            cur.execute("CREATE SEQUENCE IF NOT EXISTS photos_id_seq START 1;")
            cur.execute("CREATE SEQUENCE IF NOT EXISTS grids_id_seq START 1;")
            cur.execute("CREATE SEQUENCE IF NOT EXISTS tiles_id_seq START 1;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS photos (
                id BIGINT PRIMARY KEY DEFAULT nextval('photos_id_seq'),
                path TEXT UNIQUE NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL
                );
            """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS grids (
                id BIGINT PRIMARY KEY DEFAULT nextval('grids_id_seq'),
                photo_id BIGINT NOT NULL,
                tile_w INTEGER NOT NULL,
                tile_h INTEGER NOT NULL,
                cols INTEGER NOT NULL,
                rows INTEGER NOT NULL,
                UNIQUE(photo_id, tile_w, tile_h)
                );
            """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tiles (
                id BIGINT PRIMARY KEY DEFAULT nextval('tiles_id_seq'),
                grid_id BIGINT NOT NULL,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL,
                l DOUBLE NOT NULL, a DOUBLE NOT NULL, b DOUBLE NOT NULL
                );
            """
            )
        self.conn.commit()

    # --- create INDEXES (safe to run after data is clean) ---
    def ensure_indexes(self) -> None:
        cur = self.conn.cursor()
        cur.execute("CREATE INDEX IF NOT EXISTS tiles_grid_id_idx ON tiles(grid_id);")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS tiles_grid_xy_unique ON tiles(grid_id, x, y);")
        cur.execute("CREATE INDEX IF NOT EXISTS grids_photo_idx ON grids(photo_id);")
        self.conn.commit()

    def wipe_all(self) -> None:
        """Delete all rows; keep schema. Tolerant if tables don't exist."""
        cur = self.conn.cursor()
        for tbl in ("tiles", "photos"):
            try:
                cur.execute(f"DELETE FROM {tbl};")
            except Exception:
                pass
        if self.engine == "duckdb":
            try:
                cur.execute("ALTER SEQUENCE tiles_id_seq RESTART WITH 1;")
                cur.execute("ALTER SEQUENCE photos_id_seq RESTART WITH 1;")
            except Exception:
                pass
        self.conn.commit()

    def drop_all(self) -> None:
        """Drop tables (and sequences on DuckDB). Safe if they don't exist."""
        cur = self.conn.cursor()
        # Drop child tables first
        cur.execute("DROP TABLE IF EXISTS tiles;")
        cur.execute("DROP TABLE IF EXISTS grids;")
        cur.execute("DROP TABLE IF EXISTS photos;")

        if self.engine == "duckdb":
            # Use IF EXISTS (not IF NOT EXISTS). Guard with try in case very old versions.
            for seq in ("tiles_id_seq", "grids_id_seq", "photos_id_seq"):
                try:
                    cur.execute(f"DROP SEQUENCE IF EXISTS {seq};")
                except Exception:
                    pass

        self.conn.commit()

    def upsert_photo(self, path: Path, width: int, height: int) -> int:
        cur = self.conn.cursor()
        if self.engine == "sqlite":
            cur.execute("INSERT OR IGNORE INTO photos(path,width,height) VALUES (?,?,?)", (str(path), width, height))
        else:
            cur.execute(
                "INSERT INTO photos(path,width,height) VALUES (?,?,?) ON CONFLICT (path) DO NOTHING",
                (str(path), width, height),
            )
        cur.execute("SELECT id FROM photos WHERE path=?", (str(path),))
        return int(cur.fetchone()[0])

    def upsert_grid(self, photo_id: int, tile_w: int, tile_h: int, cols: int, rows: int) -> int:
        cur = self.conn.cursor()
        if self.engine == "sqlite":
            cur.execute(
                "INSERT OR IGNORE INTO grids(photo_id,tile_w,tile_h,cols,rows) VALUES (?,?,?,?,?)",
                (photo_id, tile_w, tile_h, cols, rows),
            )
        else:
            cur.execute(
                "INSERT INTO grids(photo_id,tile_w,tile_h,cols,rows) VALUES (?,?,?,?,?) "
                "ON CONFLICT (photo_id, tile_w, tile_h) DO NOTHING",
                (photo_id, tile_w, tile_h, cols, rows),
            )
        cur.execute("SELECT id FROM grids WHERE photo_id=? AND tile_w=? AND tile_h=?", (photo_id, tile_w, tile_h))
        return int(cur.fetchone()[0])

    def has_tiles_for_grid(self, grid_id: int) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM tiles WHERE grid_id=? LIMIT 1", (grid_id,))
        return cur.fetchone() is not None

    def delete_tiles_for_grid(self, grid_id: int) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM tiles WHERE grid_id=?", (grid_id,))
        self.conn.commit()

    def insert_tiles(self, grid_id: int, rows: list[tuple[int, int, float, float, float]]) -> None:
        # rows: (x, y, L, A, B)
        cur = self.conn.cursor()
        if self.engine == "sqlite":
            cur.executemany(
                "INSERT OR IGNORE INTO tiles (grid_id,x,y,l,a,b) VALUES (?,?,?,?,?,?)",
                [(grid_id, x, y, l, a, b) for (x, y, l, a, b) in rows],
            )
        else:
            cur.executemany(
                "INSERT INTO tiles (grid_id,x,y,l,a,b) VALUES (?,?,?,?,?,?) " "ON CONFLICT (grid_id, x, y) DO NOTHING",
                [(grid_id, x, y, l, a, b) for (x, y, l, a, b) in rows],
            )
        self.conn.commit()

    def all_tile_vectors(self) -> tuple[list[int], np.ndarray]:
        cur = self.conn.cursor()
        cur.execute("SELECT id, l, a, b FROM tiles")
        data = cur.fetchall()
        ids = [int(r[0]) for r in data]
        vecs = np.array([[r[1], r[2], r[3]] for r in data], dtype=np.float32)
        return ids, vecs

    def tile_patch_info(self, tile_id: int) -> tuple[str, int, int, int, int]:
        """
        Returns (photo_path, x, y, tile_w, tile_h) for a tile id.
        """
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT p.path, t.x, t.y, g.tile_w, g.tile_h
            FROM tiles t
            JOIN grids g ON t.grid_id = g.id
            JOIN photos p ON g.photo_id = p.id
            WHERE t.id=?
            """,
            (tile_id,),
        )
        path, x, y, tw, th = cur.fetchone()
        return path, int(x), int(y), int(tw), int(th)

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

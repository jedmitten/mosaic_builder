from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

import numpy as np


class SqlTileStore:
    def __init__(self, conn, engine: str):
        self.conn = conn
        self.engine = engine  # "sqlite" | "duckdb"

    def ensure_schema(self) -> None:
        cur = self.conn.cursor()
        if self.engine == "sqlite":
            # tables
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
                CREATE TABLE IF NOT EXISTS tiles (
                  id INTEGER PRIMARY KEY,
                  photo_id INT NOT NULL,
                  x INT NOT NULL,
                  y INT NOT NULL,
                  tile_w INT NOT NULL,
                  tile_h INT NOT NULL,
                  l REAL NOT NULL,
                  a REAL NOT NULL,
                  b REAL NOT NULL
                );
            """
            )
            # unique index to make ingest idempotent
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS tiles_photo_xy_unique ON tiles(photo_id, x, y);"
            )
            # helpful index for lookups
            cur.execute(
                "CREATE INDEX IF NOT EXISTS tiles_photo_id_idx ON tiles(photo_id);"
            )

        else:  # duckdb
            # sequences (older/newer DuckDB friendly)
            cur.execute("CREATE SEQUENCE IF NOT EXISTS photos_id_seq START 1;")
            cur.execute("CREATE SEQUENCE IF NOT EXISTS tiles_id_seq START 1;")

            # tables
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
                CREATE TABLE IF NOT EXISTS tiles (
                  id BIGINT PRIMARY KEY DEFAULT nextval('tiles_id_seq'),
                  photo_id BIGINT NOT NULL,
                  x INTEGER NOT NULL,
                  y INTEGER NOT NULL,
                  tile_w INTEGER NOT NULL,
                  tile_h INTEGER NOT NULL,
                  l DOUBLE NOT NULL,
                  a DOUBLE NOT NULL,
                  b DOUBLE NOT NULL
                );
            """
            )
            # unique index for idempotency + lookup index
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS tiles_photo_xy_unique ON tiles(photo_id, x, y);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS tiles_photo_id_idx ON tiles(photo_id);"
            )

        self.conn.commit()

    def upsert_photo(self, path: Path, width: int, height: int) -> int:
        cur = self.conn.cursor()
        if self.engine == "sqlite":
            cur.execute(
                "INSERT OR IGNORE INTO photos(path,width,height) VALUES (?,?,?)",
                (str(path), width, height),
            )
        else:  # duckdb
            cur.execute(
                "INSERT INTO photos(path,width,height) VALUES (?,?,?) "
                "ON CONFLICT (path) DO NOTHING",
                (str(path), width, height),
            )
        cur.execute("SELECT id FROM photos WHERE path=?", (str(path),))
        return int(cur.fetchone()[0])

    def insert_tiles(
        self, rows: Iterable[Tuple[int, int, int, int, int, float, float, float]]
    ) -> None:
        cur = self.conn.cursor()
        if self.engine == "sqlite":
            # ignore duplicates if (photo_id,x,y) already present
            cur.executemany(
                "INSERT OR IGNORE INTO tiles (photo_id,x,y,tile_w,tile_h,l,a,b) VALUES (?,?,?,?,?,?,?,?)",
                rows,
            )
        else:  # duckdb
            # ON CONFLICT matches the unique index on (photo_id,x,y)
            cur.executemany(
                "INSERT INTO tiles (photo_id,x,y,tile_w,tile_h,l,a,b) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT (photo_id, x, y) DO NOTHING",
                rows,
            )
        self.conn.commit()

    def has_tiles_for_photo(self, photo_id: int) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM tiles WHERE photo_id=? LIMIT 1", (photo_id,))
        return cur.fetchone() is not None

    def all_tile_vectors(self) -> Tuple[list[int], np.ndarray]:
        cur = self.conn.cursor()
        cur.execute("SELECT id, l, a, b FROM tiles")
        data = cur.fetchall()
        ids = [int(r[0]) for r in data]
        vecs = np.array([[r[1], r[2], r[3]] for r in data], dtype=np.float32)
        return ids, vecs

    def tile_patch_info(self, tile_id: int):
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT photos.path, tiles.x, tiles.y, tiles.tile_w, tiles.tile_h
            FROM tiles JOIN photos ON tiles.photo_id = photos.id
            WHERE tiles.id=?
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

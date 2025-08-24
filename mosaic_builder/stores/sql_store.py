from __future__ import annotations
from pathlib import Path
from typing import Iterable, Tuple
import numpy as np


# Accept either sqlite3 or duckdb — both are DB-API 2.0 and use "qmark" (?)
class SqlTileStore:
    def __init__(self, conn):
        self.conn = conn

    def ensure_schema(self) -> None:
        self.conn.executescript(
            """
        CREATE TABLE IF NOT EXISTS photos (
          id INTEGER PRIMARY KEY,
          path TEXT UNIQUE NOT NULL,
          width INT NOT NULL,
          height INT NOT NULL
        );
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
        # Note: simple schema to stay cross-engine. Add FKs/indexes per backend later.

    def upsert_photo(self, path: Path, width: int, height: int) -> int:
        # portable “upsert” using INSERT OR IGNORE + SELECT id
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO photos(path,width,height) VALUES (?,?,?)",
            (str(path), width, height),
        )
        cur.execute("SELECT id FROM photos WHERE path=?", (str(path),))
        return int(cur.fetchone()[0])

    def insert_tiles(
        self, rows: Iterable[Tuple[int, int, int, int, int, float, float, float]]
    ) -> None:
        self.conn.executemany(
            "INSERT INTO tiles (photo_id,x,y,tile_w,tile_h,l,a,b) VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
        self.conn.commit()

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

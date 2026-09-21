"""DuckDB store helpers — schema, read layer, and upsert operations."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import duckdb

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE SEQUENCE IF NOT EXISTS images_id_seq START 1;
    """,
    """
    CREATE TABLE IF NOT EXISTS images (
        image_id INTEGER PRIMARY KEY DEFAULT nextval('images_id_seq'),
        path TEXT UNIQUE NOT NULL,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tiles (
        image_id INTEGER NOT NULL,
        tile_side INTEGER NOT NULL,
        tile_index INTEGER NOT NULL,
        crop_box TEXT NOT NULL,
        coverage REAL NOT NULL,
        score REAL NOT NULL,
        mean_r REAL NOT NULL,
        mean_g REAL NOT NULL,
        mean_b REAL NOT NULL,
        mean_L REAL NOT NULL,
        mean_a REAL NOT NULL,
        mean_bb REAL NOT NULL,
        tile_png BLOB NOT NULL,
        PRIMARY KEY (image_id, tile_side, tile_index)
    );
    """,
)

# Column lists used by read helpers (kept DRY)
_TILE_COLS = (
    "image_id, tile_side, tile_index, crop_box, coverage, score, "
    "mean_r, mean_g, mean_b, mean_L, mean_a, mean_bb, tile_png"
)
_TILE_COLS_NO_PNG = (
    "image_id, tile_side, tile_index, crop_box, coverage, score, "
    "mean_r, mean_g, mean_b, mean_L, mean_a, mean_bb"
)


def _tile_row_to_dict(r: tuple, *, has_png: bool = True) -> dict:
    d = {
        "image_id": r[0],
        "tile_side": r[1],
        "tile_index": r[2],
        "crop_box": r[3],
        "coverage": r[4],
        "score": r[5],
        "mean_r": r[6],
        "mean_g": r[7],
        "mean_b": r[8],
        "mean_L": r[9],
        "mean_a": r[10],
        "mean_bb": r[11],
    }
    if has_png:
        d["tile_png"] = bytes(r[12])
    return d


def normalize_db_path(db: str | Path) -> Path:
    """Return a filesystem path for DuckDB (ensuring parents exist)."""
    path = Path(db)
    if path.is_dir():
        path /= "mosaic.duckdb"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def open_database(db: str | Path = "mosaic.duckdb") -> duckdb.DuckDBPyConnection:
    """Open (and lazily create) a DuckDB file."""
    path = normalize_db_path(db)
    return duckdb.connect(str(path))


def ensure_schema(conn: duckdb.DuckDBPyConnection, statements: Iterable[str] | None = None) -> None:
    """Create required tables if they do not already exist."""
    stmts = statements or SCHEMA_STATEMENTS
    for stmt in stmts:
        conn.execute(stmt)


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def get_all_images(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    """Return all images as a list of dicts."""
    rows = conn.execute(
        "SELECT image_id, path, width, height, created_at FROM images ORDER BY image_id"
    ).fetchall()
    return [{"image_id": r[0], "path": r[1], "width": r[2], "height": r[3], "created_at": r[4]} for r in rows]


def get_tiles_for_image(conn: duckdb.DuckDBPyConnection, image_id: int) -> list[dict]:
    """Return all tiles for a given image_id."""
    rows = conn.execute(
        f"SELECT {_TILE_COLS} FROM tiles WHERE image_id = ? ORDER BY tile_index",
        [image_id],
    ).fetchall()
    return [_tile_row_to_dict(r) for r in rows]


def get_all_tiles(
    conn: duckdb.DuckDBPyConnection,
    *,
    limit: int | None = None,
    offset: int = 0,
    random_n: int | None = None,
) -> list[dict]:
    """Return tiles with optional limit/offset or random sampling."""
    if random_n is not None:
        rows = conn.execute(
            f"SELECT {_TILE_COLS} FROM tiles USING SAMPLE (? ROWS)",
            [random_n],
        ).fetchall()
    else:
        query = f"SELECT {_TILE_COLS} FROM tiles ORDER BY image_id, tile_index"
        if limit is not None:
            query += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        rows = conn.execute(query).fetchall()
    return [_tile_row_to_dict(r) for r in rows]


def get_tile_png(conn: duckdb.DuckDBPyConnection, image_id: int, tile_index: int) -> bytes:
    """Return the raw PNG bytes for a specific tile."""
    row = conn.execute(
        "SELECT tile_png FROM tiles WHERE image_id = ? AND tile_index = ?",
        [image_id, tile_index],
    ).fetchone()
    if row is None:
        raise KeyError(f"No tile found for image_id={image_id}, tile_index={tile_index}")
    return bytes(row[0])


def get_tile_lab_descriptors(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    """Bulk-fetch LAB descriptors for all tiles (no PNG blobs, fast)."""
    rows = conn.execute(f"SELECT {_TILE_COLS_NO_PNG} FROM tiles ORDER BY image_id, tile_index").fetchall()
    return [_tile_row_to_dict(r, has_png=False) for r in rows]


# ---------------------------------------------------------------------------
# Upsert helpers (transactional)
# ---------------------------------------------------------------------------


def upsert_image(
    conn: duckdb.DuckDBPyConnection,
    path: str,
    width: int,
    height: int,
) -> int:
    """Insert or replace an image row, deleting old tiles first. Returns image_id."""
    # Manual cascade: delete tiles before the image
    conn.execute(
        "DELETE FROM tiles WHERE image_id IN (SELECT image_id FROM images WHERE path = ?)",
        [path],
    )
    conn.execute("DELETE FROM images WHERE path = ?", [path])
    conn.execute(
        "INSERT INTO images (path, width, height) VALUES (?, ?, ?)",
        [path, width, height],
    )
    row = conn.execute("SELECT image_id FROM images WHERE path = ?", [path]).fetchone()
    return int(row[0])


def upsert_tiles(
    conn: duckdb.DuckDBPyConnection,
    image_id: int,
    tiles: list[dict],
) -> None:
    """Insert tiles for an image. Expects tiles already deleted via cascade."""
    for t in tiles:
        conn.execute(
            """INSERT INTO tiles
               (image_id, tile_side, tile_index, crop_box, coverage, score,
                mean_r, mean_g, mean_b, mean_L, mean_a, mean_bb, tile_png)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                image_id,
                t["tile_side"],
                t["tile_index"],
                t["crop_box"],
                t["coverage"],
                t["score"],
                t["mean_r"],
                t["mean_g"],
                t["mean_b"],
                t["mean_L"],
                t["mean_a"],
                t["mean_bb"],
                t["tile_png"],
            ],
        )

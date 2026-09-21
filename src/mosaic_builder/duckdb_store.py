"""DuckDB store helpers — schema, read layer, and upsert operations."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import duckdb

#: Bump whenever ``SCHEMA_STATEMENTS`` changes shape. There are no migrations:
#: a mismatch means "delete the .duckdb file and re-ingest".
SCHEMA_VERSION: int = 2

#: Key used in the ``schema_meta`` table to store :data:`SCHEMA_VERSION`.
_SCHEMA_VERSION_KEY = "schema_version"


class SchemaVersionError(RuntimeError):
    """Raised when a database's schema does not match :data:`SCHEMA_VERSION`."""


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
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key VARCHAR PRIMARY KEY,
        value VARCHAR NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

#: Every column the current schema expects on ``tiles`` (13 names).
EXPECTED_TILE_COLUMNS: frozenset[str] = frozenset(c.strip() for c in _TILE_COLS.split(","))


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


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------


def _table_names(conn: duckdb.DuckDBPyConnection) -> set[str]:
    """Return the names of every table visible in the current database."""
    rows = conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
    return {str(r[0]) for r in rows}


def _tile_columns(conn: duckdb.DuckDBPyConnection) -> set[str]:
    """Return the column names of the ``tiles`` table (empty set if absent)."""
    try:
        rows = conn.execute("DESCRIBE tiles").fetchall()
    except duckdb.Error:
        return set()
    return {str(r[0]) for r in rows}


def get_schema_version(conn: duckdb.DuckDBPyConnection) -> int | None:
    """Return the stored schema version, or ``None`` if it is not recorded.

    Never raises on a database without a ``schema_meta`` table.
    """
    try:
        row = conn.execute("SELECT value FROM schema_meta WHERE key = ?", [_SCHEMA_VERSION_KEY]).fetchone()
    except duckdb.Error:
        return None
    if row is None or row[0] is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def stamp_schema_version(conn: duckdb.DuckDBPyConnection, version: int = SCHEMA_VERSION) -> None:
    """Record ``version`` as the database's schema version (upsert)."""
    conn.execute("DELETE FROM schema_meta WHERE key = ?", [_SCHEMA_VERSION_KEY])
    conn.execute(
        "INSERT INTO schema_meta (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        [_SCHEMA_VERSION_KEY, str(int(version))],
    )


_DELETE_HINT = (
    "There are no migrations: delete the .duckdb file and re-ingest the gallery "
    "(uv run python -m mosaic_builder.ingest ...)."
)


def _legacy_message(conn: duckdb.DuckDBPyConnection) -> str:
    missing = sorted(EXPECTED_TILE_COLUMNS - _tile_columns(conn))
    msg = (
        "This database is out of date: it predates schema versioning "
        f"(expected schema version {SCHEMA_VERSION})."
    )
    if missing:
        msg += " Missing columns on 'tiles': " + ", ".join(missing) + "."
    return f"{msg} {_DELETE_HINT}"


def _check_tile_columns(conn: duckdb.DuckDBPyConnection) -> None:
    columns = _tile_columns(conn)
    if not columns:
        return
    missing = sorted(EXPECTED_TILE_COLUMNS - columns)
    if missing:
        raise SchemaVersionError(
            "This database is out of date: the 'tiles' table is missing "
            + ", ".join(missing)
            + f". {_DELETE_HINT}"
        )


def ensure_schema(conn: duckdb.DuckDBPyConnection, statements: Iterable[str] | None = None) -> None:
    """Create required tables if absent, then verify the schema version.

    Raises :class:`SchemaVersionError` for a database written by an older or
    newer mosaic-builder, or for one missing expected ``tiles`` columns.
    """
    # Step 1: detect a legacy database *before* creating anything, otherwise
    # creating schema_meta destroys the evidence.
    existing = _table_names(conn)
    is_legacy = ("tiles" in existing or "images" in existing) and "schema_meta" not in existing

    # Step 2: create missing tables.
    stmts = statements or SCHEMA_STATEMENTS
    for stmt in stmts:
        conn.execute(stmt)

    # Step 3: legacy databases are unreadable; there are no migrations.
    if is_legacy:
        raise SchemaVersionError(_legacy_message(conn))

    # Steps 4-6: version check.
    version = get_schema_version(conn)
    if version is None:
        stamp_schema_version(conn)
    elif version < SCHEMA_VERSION:
        raise SchemaVersionError(
            f"This database is out of date: schema version {version}, "
            f"but this mosaic-builder expects version {SCHEMA_VERSION}. {_DELETE_HINT}"
        )
    elif version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"This database has schema version {version}, which is newer than the "
            f"version {SCHEMA_VERSION} this mosaic-builder understands. "
            "Upgrade the mosaic-builder package to read it."
        )

    # Step 7: column guard.
    _check_tile_columns(conn)


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
        # DuckDB rejects bound parameters inside a SAMPLE clause, so sample by
        # ordering on random() instead.
        rows = conn.execute(
            f"SELECT {_TILE_COLS} FROM tiles ORDER BY random() LIMIT {int(random_n)}"
        ).fetchall()
    else:
        query = f"SELECT {_TILE_COLS} FROM tiles ORDER BY image_id, tile_index"
        if limit is not None:
            query += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        rows = conn.execute(query).fetchall()
    return [_tile_row_to_dict(r) for r in rows]


def get_tile_png(
    conn: duckdb.DuckDBPyConnection,
    image_id: int,
    tile_index: int,
    *,
    tile_side: int | None = None,
) -> bytes:
    """Return the raw PNG bytes for a specific tile.

    ``(image_id, tile_side, tile_index)`` is the primary key, so pass
    ``tile_side`` whenever a database could hold more than one tile side.
    """
    query = "SELECT tile_png FROM tiles WHERE image_id = ? AND tile_index = ?"
    params: list = [image_id, tile_index]
    if tile_side is not None:
        query += " AND tile_side = ?"
        params.append(tile_side)
    row = conn.execute(query, params).fetchone()
    if row is None:
        raise KeyError(
            f"No tile found for image_id={image_id}, tile_index={tile_index}, tile_side={tile_side}"
        )
    return bytes(row[0])


def get_tile_pngs_bulk(
    conn: duckdb.DuckDBPyConnection,
    keys: Iterable[tuple[int, int]],
    *,
    tile_side: int,
) -> dict[tuple[int, int], bytes]:
    """Fetch many tile PNGs in one query.

    ``keys`` is an iterable of ``(image_id, tile_index)``. Keys with no matching
    row are simply absent from the returned dict; nothing is raised.
    """
    unique_keys = list(dict.fromkeys((int(i), int(t)) for i, t in keys))
    if not unique_keys:
        return {}
    pairs = ", ".join(["(?, ?)"] * len(unique_keys))
    params: list = [tile_side]
    for image_id, tile_index in unique_keys:
        params.extend((image_id, tile_index))
    rows = conn.execute(
        "SELECT image_id, tile_index, tile_png FROM tiles "
        f"WHERE tile_side = ? AND (image_id, tile_index) IN ({pairs})",
        params,
    ).fetchall()
    return {(int(r[0]), int(r[1])): bytes(r[2]) for r in rows}


def get_tile_sides(conn: duckdb.DuckDBPyConnection) -> list[int]:
    """Return every distinct ``tile_side`` present in the database, ascending."""
    rows = conn.execute("SELECT DISTINCT tile_side FROM tiles ORDER BY tile_side").fetchall()
    return [int(r[0]) for r in rows]


def get_tile_lab_descriptors(conn: duckdb.DuckDBPyConnection, *, tile_side: int | None = None) -> list[dict]:
    """Bulk-fetch LAB descriptors for all tiles (no PNG blobs, fast)."""
    query = f"SELECT {_TILE_COLS_NO_PNG} FROM tiles"
    params: list = []
    if tile_side is not None:
        query += " WHERE tile_side = ?"
        params.append(tile_side)
    query += " ORDER BY image_id, tile_index"
    rows = conn.execute(query, params).fetchall()
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

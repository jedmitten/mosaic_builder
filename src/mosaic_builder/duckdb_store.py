"""DuckDB store helpers — schema, read layer, and upsert operations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import duckdb

#: Bump whenever :data:`TILE_COLUMNS` (or any other schema statement) changes
#: shape. There are no migrations: a mismatch means "delete the .duckdb file
#: and re-ingest". That is cheap because the database is a derived cache — the
#: photo gallery is the source of truth.
SCHEMA_VERSION: int = 4

#: Key used in the ``schema_meta`` table to store :data:`SCHEMA_VERSION`.
_SCHEMA_VERSION_KEY = "schema_version"


class SchemaVersionError(RuntimeError):
    """Raised when a database's schema does not match :data:`SCHEMA_VERSION`."""


@dataclass(frozen=True)
class TileColumn:
    """One column of the ``tiles`` table."""

    name: str
    sql_type: str
    #: Large payload: excluded from descriptor reads and wrapped in ``bytes()``.
    blob: bool = False


#: The single source of truth for the ``tiles`` table. The DDL, both SELECT
#: column lists, the row-to-dict mapping, and the INSERT statement are all
#: derived from this tuple, so adding a per-tile feature means adding one entry
#: here (plus supplying the value in ingest.py) and bumping SCHEMA_VERSION.
#:
#: Only *measured* values belong here. Scores derived from other columns plus
#: tunable constants — e.g. tiler.fixture_likelihood_score — are deliberately
#: not stored: they are computed on read so retuning a constant takes effect
#: without re-ingesting.
TILE_COLUMNS: tuple[TileColumn, ...] = (
    TileColumn("image_id", "INTEGER"),
    TileColumn("tile_side", "INTEGER"),
    TileColumn("tile_index", "INTEGER"),
    TileColumn("crop_box", "TEXT"),
    TileColumn("coverage", "REAL"),
    TileColumn("score", "REAL"),
    TileColumn("mean_r", "REAL"),
    TileColumn("mean_g", "REAL"),
    TileColumn("mean_b", "REAL"),
    TileColumn("mean_L", "REAL"),
    TileColumn("mean_a", "REAL"),
    TileColumn("mean_bb", "REAL"),
    TileColumn("color_contrast", "REAL"),
    TileColumn("periodicity", "REAL"),
    TileColumn("tile_png", "BLOB", blob=True),
)

#: Columns of the composite primary key, in order.
_TILE_PRIMARY_KEY: tuple[str, ...] = ("image_id", "tile_side", "tile_index")

#: Columns returned by descriptor reads (everything except large blobs).
TILE_DESCRIPTOR_COLUMNS: tuple[TileColumn, ...] = tuple(c for c in TILE_COLUMNS if not c.blob)


def _column_list(columns: Iterable[TileColumn]) -> str:
    """Comma-joined column names for a SELECT/INSERT list."""
    return ", ".join(c.name for c in columns)


def _tiles_ddl() -> str:
    """Build the ``tiles`` CREATE TABLE from :data:`TILE_COLUMNS`."""
    definitions = ",\n        ".join(f"{c.name} {c.sql_type} NOT NULL" for c in TILE_COLUMNS)
    return f"""
    CREATE TABLE IF NOT EXISTS tiles (
        {definitions},
        PRIMARY KEY ({", ".join(_TILE_PRIMARY_KEY)})
    );
    """


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
    _tiles_ddl(),
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key VARCHAR PRIMARY KEY,
        value VARCHAR NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
)

# Column lists used by read helpers
_TILE_COLS = _column_list(TILE_COLUMNS)
_TILE_COLS_NO_PNG = _column_list(TILE_DESCRIPTOR_COLUMNS)

#: Every column the current schema expects on ``tiles``.
EXPECTED_TILE_COLUMNS: frozenset[str] = frozenset(c.name for c in TILE_COLUMNS)


def _tile_row_to_dict(r: tuple, *, has_png: bool = True) -> dict:
    """Map a row tuple onto column names.

    Zips against :data:`TILE_COLUMNS` rather than indexing by position, so
    inserting a column cannot silently shift values into the wrong keys.
    """
    columns = TILE_COLUMNS if has_png else TILE_DESCRIPTOR_COLUMNS
    return {c.name: bytes(value) if c.blob else value for c, value in zip(columns, r, strict=True)}


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
    """Insert tiles for an image. Expects tiles already deleted via cascade.

    Every column in :data:`TILE_COLUMNS` except ``image_id`` must be present in
    each tile dict; a missing key raises ``KeyError`` naming the column.
    """
    placeholders = ", ".join(["?"] * len(TILE_COLUMNS))
    statement = f"INSERT INTO tiles ({_TILE_COLS}) VALUES ({placeholders})"
    for t in tiles:
        conn.execute(
            statement,
            [image_id if c.name == "image_id" else t[c.name] for c in TILE_COLUMNS],
        )

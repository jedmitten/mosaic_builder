"""Minimal DuckDB store helpers for the rebuilt project."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import duckdb

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS images (
        image_id INTEGER PRIMARY KEY,
        path TEXT UNIQUE NOT NULL,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tiles (
        image_id INTEGER NOT NULL REFERENCES images(image_id),
        tile_index INTEGER NOT NULL,
        crop_box TEXT NOT NULL,
        coverage REAL NOT NULL,
        score REAL NOT NULL,
        mean_r REAL NOT NULL,
        mean_g REAL NOT NULL,
        mean_b REAL NOT NULL,
        descriptor BLOB NOT NULL,
        tile_png BLOB NOT NULL,
        PRIMARY KEY (image_id, tile_index)
    );
    """,
)


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

from __future__ import annotations
from urllib.parse import urlparse
from pathlib import Path
from mosaic_builder.stores.sql_store import SqlTileStore


def open_store(url: str):
    """
    url examples:
      sqlite:///mosaic.db
      duckdb:///mosaic.duckdb
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    path = Path(parsed.path.lstrip("/")) if parsed.path else Path("mosaic.db")

    if scheme == "sqlite":
        import sqlite3

        conn = sqlite3.connect(path)
        # speed ups for local, safe single-user workloads:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return SqlTileStore(conn)

    if scheme == "duckdb":
        import duckdb  # optional extra

        conn = duckdb.connect(str(path))
        return SqlTileStore(conn)

    raise ValueError(f"Unsupported store URL scheme: {scheme}")

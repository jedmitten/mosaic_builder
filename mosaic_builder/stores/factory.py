from pathlib import Path
from urllib.parse import urlparse

from mosaic_builder.stores.sql_store import SqlTileStore


def open_store(url: str):
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    path = Path(parsed.path.lstrip("/")) or Path("mosaic.db")

    if scheme == "sqlite":
        import sqlite3

        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return SqlTileStore(conn, engine="sqlite")

    if scheme == "duckdb":
        import duckdb

        conn = duckdb.connect(str(path))
        return SqlTileStore(conn, engine="duckdb")

    raise ValueError(f"Unsupported store URL scheme: {scheme}")

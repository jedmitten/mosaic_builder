from pathlib import Path
from urllib.parse import urlparse

from mosaic_builder.stores.base import BaseTileStore
from mosaic_builder.stores.registry import TileStoreRegistry


def open_store(url: str, *, no_init: bool = False) -> BaseTileStore:
    """Open a tile store with the given URL.

    Args:
        url: Store URL (e.g., "sqlite:///mosaic.db")
        no_init: If True, don't initialize the store (useful for closing/cleanup)

    Returns:
        An initialized tile store instance
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "duckdb"  # Default to sqlite if no scheme
    path = Path(parsed.path.lstrip("/")) if parsed.path else None

    # Get the store class from registry
    store_class = TileStoreRegistry.get_store(scheme)
    store = store_class(engine=scheme)

    if not no_init:
        # Initialize with default path if none provided
        default_path = "mosaic.duckdb" if scheme == "duckdb" else "mosaic.db"
        path = path or Path(default_path)
        store.initialize(path=path)
        store.ensure_schema()
        store.ensure_indexes()

    return store

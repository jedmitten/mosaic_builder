"""Core package initialization."""

from importlib import metadata

from .duckdb_store import (
    SCHEMA_VERSION,
    SchemaVersionError,
    ensure_schema,
    get_all_images,
    get_all_tiles,
    get_schema_version,
    get_tile_lab_descriptors,
    get_tile_png,
    get_tile_pngs_bulk,
    get_tile_sides,
    get_tiles_for_image,
    open_database,
    upsert_image,
    upsert_tiles,
)

__all__ = [
    "SCHEMA_VERSION",
    "SchemaVersionError",
    "open_database",
    "ensure_schema",
    "get_schema_version",
    "get_all_images",
    "get_tiles_for_image",
    "get_all_tiles",
    "get_tile_png",
    "get_tile_lab_descriptors",
    "get_tile_pngs_bulk",
    "get_tile_sides",
    "upsert_image",
    "upsert_tiles",
    "__version__",
]


def _package_version() -> str:
    try:
        return metadata.version("mosaic-builder")
    except metadata.PackageNotFoundError:
        return "0.0.0"


__version__ = _package_version()

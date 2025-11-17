"""Core package initialization"""

from importlib import metadata

from .duckdb_store import ensure_schema, open_database
from .ingest import ingest_gallery
from .preview import render_preview

__all__ = ["open_database", "ensure_schema", "ingest_gallery", "render_preview", "__version__"]


def _package_version() -> str:
    try:
        return metadata.version("mosaic-builder")
    except metadata.PackageNotFoundError:
        return "0.0.0"


__version__ = _package_version()

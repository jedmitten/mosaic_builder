"""Shared test helpers.

``make_tile`` is the single place tests build a tile dict for
``upsert_tiles``, so adding a column to ``duckdb_store.TILE_COLUMNS`` means
updating one default here rather than every test module.
"""

from __future__ import annotations

from mosaic_builder.duckdb_store import TILE_COLUMNS

#: Defaults for every ``TILE_COLUMNS`` entry except ``image_id``, which
#: ``upsert_tiles`` supplies from its own argument.
_TILE_DEFAULTS: dict = {
    "tile_side": 32,
    "tile_index": 0,
    "crop_box": "0,0,32,32",
    "coverage": 0.5,
    "score": 1.0,
    "mean_r": 100.0,
    "mean_g": 50.0,
    "mean_b": 25.0,
    "mean_L": 45.0,
    "mean_a": 12.0,
    "mean_bb": -8.0,
    "color_contrast": 0.0,
    "periodicity": 0.0,
    "tile_png": b"\x89PNG",
}


def make_tile(**overrides) -> dict:
    """Return a complete tile dict, with any field overridden by keyword."""
    missing = {c.name for c in TILE_COLUMNS} - {"image_id"} - _TILE_DEFAULTS.keys()
    if missing:
        raise AssertionError(f"_TILE_DEFAULTS needs entries for new schema columns: {sorted(missing)}")
    return {**_TILE_DEFAULTS, **overrides}

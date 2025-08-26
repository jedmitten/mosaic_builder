from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# TOML loader (py3.11+: tomllib; py3.10 fallback to tomli if installed)
try:
    import tomllib
except ModuleNotFoundError:  # py310 fallback
    import tomli as tomllib

DEFAULT_SEARCH_PATHS = [
    Path("./mosaic.toml"),
    Path("./mosaic_builder.toml"),
    Path.home() / ".config" / "mosaic_builder" / "config.toml",
]


@dataclass
class AppConfig:
    # core
    photos_src: Path | None = None
    store_url: str = "sqlite:///mosaic.db"
    index_path: Path = Path("tiles_kdtree.joblib")
    tile_px: int = 24


def _load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_config(explicit_path: Path | None = None) -> AppConfig:
    cfg = AppConfig()

    # 1) Config file (explicit, then first existing default)
    data: dict = {}
    if explicit_path and explicit_path.exists():
        data = _load_toml(explicit_path)
    else:
        for p in DEFAULT_SEARCH_PATHS:
            if p.exists():
                data = _load_toml(p)
                break

    section = data.get("mosaic_builder", data)  # allow root or [mosaic_builder]

    if "photos_src" in section:
        cfg.photos_src = Path(section["photos_src"])
    if "store_url" in section:
        cfg.store_url = str(section["store_url"])
    if "index_path" in section:
        cfg.index_path = Path(section["index_path"])
    if "tile_px" in section:
        cfg.tile_px = int(section["tile_px"])

    # 2) Environment overrides (optional)
    if os.getenv("MOSAIC_PHOTOS_SRC"):
        cfg.photos_src = Path(os.getenv("MOSAIC_PHOTOS_SRC", ""))
    if os.getenv("MOSAIC_STORE_URL"):
        cfg.store_url = os.getenv("MOSAIC_STORE_URL", cfg.store_url)
    if os.getenv("MOSAIC_INDEX_PATH"):
        cfg.index_path = Path(os.getenv("MOSAIC_INDEX_PATH", str(cfg.index_path)))
    if os.getenv("MOSAIC_TILE_PX"):
        cfg.tile_px = int(os.getenv("MOSAIC_TILE_PX", cfg.tile_px))

    return cfg

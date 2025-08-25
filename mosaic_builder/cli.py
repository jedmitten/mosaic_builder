from __future__ import annotations

from pathlib import Path

import typer

from mosaic_builder.config import AppConfig, load_config
from mosaic_builder.index.build_index import build_kdtree
from mosaic_builder.pipeline.build_mosaic import build_mosaic
from mosaic_builder.pipeline.ingest import ingest_dir

app = typer.Typer(add_completion=False)


def _resolve_cfg(
    config_path: Path | None,
    photos_src: Path | None,
    store: str | None,
    index_path: Path | None,
    tile_px: int | None,
) -> AppConfig:
    cfg = load_config(config_path)

    # CLI overrides (highest precedence)
    if photos_src is not None:
        cfg.photos_src = photos_src
    if store is not None:
        cfg.store_url = store
    if index_path is not None:
        cfg.index_path = index_path
    if tile_px is not None:
        cfg.tile_px = tile_px

    return cfg


@app.command()
def ingest(
    images_dir: Path | None = typer.Option(None),
    config: Path | None = typer.Option(None, "--config", "-c"),
    store: str | None = typer.Option(None),
    tile_px: int | None = typer.Option(None),
    debug_dir: Path | None = typer.Option(None, help="Save debug images here"),
):
    cfg = _resolve_cfg(config, images_dir, store, None, tile_px)
    if cfg.photos_src is None:
        raise typer.BadParameter("photos_src not provided.")
    ingest_dir(cfg.store_url, cfg.photos_src, cfg.tile_px, cfg.tile_px, debug_dir)


@app.command()
def index(
    config: Path | None = typer.Option(None, "--config", "-c"),
    store: str | None = typer.Option(None),
    index_path: Path | None = typer.Option(None),
    debug_dir: Path | None = typer.Option(None, help="Save debug images here"),
):
    cfg = _resolve_cfg(config, None, store, index_path, None)
    build_kdtree(cfg.store_url, cfg.index_path, debug_dir)


@app.command()
def build(
    target: Path,
    out: Path = Path("out.png"),
    config: Path | None = typer.Option(None, "--config", "-c"),
    store: str | None = typer.Option(None),
    index_path: Path | None = typer.Option(None),
    tile_px: int | None = typer.Option(None),
    debug_dir: Path | None = typer.Option(None, help="Save debug images here"),
):
    cfg = _resolve_cfg(config, None, store, index_path, tile_px)
    build_mosaic(
        cfg.store_url, cfg.index_path, target, out, cfg.tile_px, cfg.tile_px, debug_dir
    )


if __name__ == "__main__":
    app()

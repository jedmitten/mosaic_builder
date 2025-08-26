from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import typer

from mosaic_builder.config import AppConfig, load_config
from mosaic_builder.index.build_index import build_kdtree
from mosaic_builder.pipeline.build_mosaic import build_mosaic
from mosaic_builder.pipeline.ingest import ingest_dir
from mosaic_builder.stores.factory import open_store

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
    debug_dir: Path | None = typer.Option(None),
    reingest: bool = typer.Option(False, help="Recompute tiles for this grid size if it already exists."),
):
    cfg = _resolve_cfg(config, images_dir, store, None, tile_px)
    if cfg.photos_src is None:
        raise typer.BadParameter("photos_src not provided.")
    ingest_dir(cfg.store_url, cfg.photos_src, cfg.tile_px, cfg.tile_px, debug_dir, reingest=reingest)


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
    build_mosaic(cfg.store_url, cfg.index_path, target, out, cfg.tile_px, cfg.tile_px, debug_dir)


@app.command()
def reset_db(
    store: str = typer.Option(
        "sqlite:///mosaic.db",
        help='DB URL, e.g. "sqlite:///mosaic.db" or "duckdb:///mosaic.duckdb"',
    ),
    mode: str = typer.Option(
        "wipe",
        help='"wipe" = delete rows; keep schema. "drop" = drop & recreate schema.',
    ),
    nuke: bool = typer.Option(False, help="Delete the database file itself (dangerous)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """
    Reset the database so you can start over.
    """
    # Parse path for possible --nuke
    parsed = urlparse(store)
    db_path = (parsed.path or "").lstrip("/")

    if not yes:
        msg = "This will "
        if nuke:
            msg += f"DELETE the DB file at '{db_path}'."
        elif mode == "drop":
            msg += "DROP and recreate all tables."
        else:
            msg += "DELETE all rows (keeping schema)."
        typer.confirm(f"{msg} Continue?", abort=True)

    if nuke:
        # Close any open handle by opening/closing once
        s = open_store(store)
        try:
            s.close()
        finally:
            pass
        if db_path:
            try:
                os.remove(db_path)
                typer.echo(f"[mosaic-builder] Deleted DB file: {db_path}")
            except FileNotFoundError:
                typer.echo(f"[mosaic-builder] DB file not found: {db_path}")
        return

    s = open_store(store)
    try:
        if mode == "wipe":
            s.wipe_all()  # 1) clear data first
            s.ensure_schema()  # 2) make sure tables exist
            s.ensure_indexes()  # 3) (re)create indexes now that data is clean
            typer.echo("[mosaic-builder] Database wiped (rows deleted), schema & indexes ensured.")
        elif mode == "drop":
            s.drop_all()
            s.ensure_schema()
            s.ensure_indexes()
            typer.echo("[mosaic-builder] Database dropped and recreated (schema + indexes).")
        else:
            raise typer.BadParameter('mode must be "wipe" or "drop"')
    finally:
        s.close()


if __name__ == "__main__":
    app()

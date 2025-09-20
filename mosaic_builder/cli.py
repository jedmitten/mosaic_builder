"""Command-line interface for mosaic builder."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import typer

from mosaic_builder.config import AppConfig, load_config
from mosaic_builder.index.build_index import build_kdtree
from mosaic_builder.pipeline.base import BuildMosaicPipeline, IngestPipeline
from mosaic_builder.stores import open_store

app = typer.Typer(
    name="mosaic-builder",
    help="Build photo mosaics from a collection of images",
    add_completion=False,
    no_args_is_help=True,  # Show help when no arguments are provided
    context_settings={"help_option_names": ["-h", "--help"]},  # Explicitly enable -h
)


def _resolve_cfg(
    config_path: Path | None = None,
    photos_src: Path | None = None,
    store: str | None = None,
    index_path: Path | None = None,
    tile_px: int | None = None,
    no_defaults: bool = False,
) -> AppConfig:
    """Resolve configuration from multiple sources."""
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

    # Ensure we have a store URL unless explicitly disabled
    if not no_defaults and not cfg.store_url:
        cfg.store_url = "sqlite:///mosaic.db"

    return cfg


@app.command()
def ingest(
    images_dir: Path | None = typer.Option(
        None,
        "--images-dir",
        "-i",
        help="Directory containing images to process into tiles",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config file (default: ./mosaic.toml)",
    ),
    store: str | None = typer.Option(
        None,
        help="Database URL (e.g., sqlite:///mosaic.db or duckdb:///mosaic.duckdb)",
    ),
    tile_px: int | None = typer.Option(
        None,
        "--tile-px",
        "-t",
        help="Tile size in pixels (default: 24)",
    ),
    debug_dir: Path | None = typer.Option(
        None,
        "--debug-dir",
        "-d",
        help="Save debug images to this directory",
    ),
    reingest: bool = typer.Option(
        False,
        help="Recompute tiles for this grid size if it already exists",
    ),
    no_defaults: bool = typer.Option(
        False,
        help="Don't use default settings from config",
    ),
):
    """Process a directory of images into tiles for creating mosaics.

    This command will:
    1. Scan the images directory recursively
    2. Process each image into a grid of tiles
    3. Store tile information in the database

    The processed tiles can then be used by the 'build' command to create mosaics.
    """
    cfg = _resolve_cfg(config, images_dir, store, None, tile_px, no_defaults)
    if cfg.photos_src is None:
        raise typer.BadParameter("photos_src not provided.")

    store = open_store(cfg.store_url)
    try:
        pipeline = IngestPipeline(store)
        pipeline.run(
            images_dir=cfg.photos_src,
            tile_w=cfg.tile_px,
            tile_h=cfg.tile_px,
            debug_dir=debug_dir,
            reingest=reingest,
        )
    finally:
        store.close()


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
    target: Path | None = typer.Option(
        None,
        "--target",
        "-t",
        help="Path to reference image to recreate as a mosaic",
    ),
    prompt: str | None = typer.Option(
        None,
        "--prompt",
        "-p",
        help="Generate source image with AI using this prompt",
    ),
    out: Path = typer.Option(
        Path("mosaic.png"),
        "--out",
        "-o",
        help="Output path for the mosaic image",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config file (default: ./mosaic.toml)",
    ),
    store: str | None = typer.Option(
        None,
        help="Database URL (e.g., sqlite:///mosaic.db or duckdb:///mosaic.duckdb)",
    ),
    index_path: Path | None = typer.Option(
        None,
        help="Path to the tile index file (default: tiles_kdtree.joblib)",
    ),
    tile_px: int | None = typer.Option(
        None,
        help="Tile size in pixels (default: 24)",
    ),
    debug_dir: Path | None = typer.Option(
        None,
        "--debug-dir",
        "-d",
        help="Save debug images to this directory",
    ),
    no_defaults: bool = typer.Option(
        False,
        help="Don't use default settings from config",
    ),
):
    """Create a mosaic from a source image using the tile database.

    There are two ways to specify the source image:
    1. --target: Use an existing image file
    2. --prompt: Generate an image using AI (requires OpenAI API key)

    The command will:
    1. Get the source image (from file or AI)
    2. Break it into a grid
    3. Find the best matching tiles from the database
    4. Assemble the final mosaic

    Make sure to run 'ingest' first to populate the tile database.
    """
    from mosaic_builder.pipeline.source_image import (
        AIImageProvider,
        ReferenceImageProvider,
    )

    if target and prompt:
        raise typer.BadParameter("Cannot specify both target and prompt. Choose one method.")
    if not target and not prompt:
        raise typer.BadParameter("Must specify either --target or --prompt")

    cfg = _resolve_cfg(config, None, store, index_path, tile_px, no_defaults)

    # Debugging: Log the target path
    if target:
        print(f"[DEBUG] Target path received: {target}")

    # Get the source image
    if target:
        provider = ReferenceImageProvider(target)
    else:
        provider = AIImageProvider(prompt)

    source_image, source_desc = provider.get_source_image()

    # Debugging: Confirm source image processing
    print(f"[DEBUG] Source image description: {source_desc}")

    # If using AI-generated image, save it for reference
    if not target and prompt:
        ai_source = out.parent / f"{out.stem}_source{out.suffix}"
        source_image.save(ai_source)
        print(f"AI-generated source image saved to: {ai_source}")
        print(f"Prompt used: {source_desc}")

    store = open_store(cfg.store_url)
    try:
        pipeline = BuildMosaicPipeline(store)
        pipeline.run(
            source_image=source_image,  # Pass the processed image object
            out=out,
            index_path=cfg.index_path,
            tile_w=cfg.tile_px,
            tile_h=cfg.tile_px,
            debug_dir=debug_dir,
        )
    finally:
        store.close()


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

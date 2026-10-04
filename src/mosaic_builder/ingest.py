"""DuckDB ingestion helpers for mosaic tiles."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from .cli import cli_errors
from .duckdb_store import ensure_schema, open_database, upsert_image, upsert_tiles
from .progress import iter_with_progress
from .tiler import (
    color_contrast_score,
    extract_character_tiles,
    iter_gallery_images,
    load_image,
    mean_lab,
    mean_rgb,
    periodicity_score,
    resize_tile,
    tile_png_bytes,
)

# Backwards-compatible alias; the implementation now lives in progress.py.
_iter_with_progress = iter_with_progress


@dataclass(frozen=True)
class IngestSummary:
    images: int
    tiles: int


def ingest_gallery(
    images_dir: Path,
    db_path: Path,
    *,
    tile_side: int = 48,
    max_tiles: int = 3,
    show_progress: bool = True,
) -> IngestSummary:
    """Ingest a gallery directory into the database. Returns a summary."""
    conn = open_database(db_path)
    ensure_schema(conn)
    paths = list(iter_gallery_images(images_dir))
    progress_iter = iter_with_progress(paths, desc="Ingesting images", enabled=show_progress)
    image_count = 0
    tile_count = 0
    try:
        for image_path in progress_iter:
            base = load_image(image_path)
            w, h = base.size

            conn.execute("BEGIN TRANSACTION")
            try:
                # Resolve before storing: a relative path is only meaningful
                # from the directory ingest happened to run in, which breaks
                # every later reader that has a different working directory.
                image_id = upsert_image(conn, str(image_path.resolve()), w, h)
                raw_tiles = extract_character_tiles(base, max_tiles=max_tiles)
                tile_dicts = []
                for idx, tile_crop in enumerate(raw_tiles):
                    resized = resize_tile(tile_crop.image, tile_side)
                    crop_area = tile_crop.image.width * tile_crop.image.height
                    image_area = w * h
                    coverage = float(crop_area / image_area) if image_area > 0 else 0.0
                    r, g, b = mean_rgb(resized)
                    L, a, bb = mean_lab(resized)
                    cc = color_contrast_score(resized)
                    per = periodicity_score(resized)
                    tile_dicts.append(
                        {
                            "tile_side": tile_side,
                            "tile_index": idx,
                            "crop_box": ",".join(map(str, tile_crop.box)),
                            "coverage": coverage,
                            "score": float(tile_crop.score),
                            "mean_r": float(r),
                            "mean_g": float(g),
                            "mean_b": float(b),
                            "mean_L": float(L),
                            "mean_a": float(a),
                            "mean_bb": float(bb),
                            "color_contrast": float(cc),
                            "periodicity": float(per),
                            "tile_png": tile_png_bytes(resized),
                        }
                    )
                upsert_tiles(conn, image_id, tile_dicts)
                conn.execute("COMMIT")
                image_count += 1
                tile_count += len(tile_dicts)
            except Exception:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()
    return IngestSummary(images=image_count, tiles=tile_count)


def build_parser(sub: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    """Build this module's parser, standalone or attached to a subparsers action."""
    description = "Ingest a gallery into the mosaic database."
    parser = (
        sub.add_parser("ingest", description=description, help=description)
        if sub is not None
        else argparse.ArgumentParser(description=description)
    )
    parser.add_argument("images_dir", type=Path)
    parser.add_argument("--db", type=Path, default=Path("mosaic.duckdb"))
    parser.add_argument("--tile-side", type=int, default=64)
    parser.add_argument("--max-tiles", type=int, default=3)
    parser.add_argument("--no-progress", action="store_true", help="Disable progress output")
    parser.set_defaults(handler=run_from_args)
    return parser


def run_from_args(args: argparse.Namespace) -> None:
    """Run ingestion from parsed arguments. Shared by this CLI and the dispatcher."""
    if not Path(args.images_dir).is_dir():
        raise FileNotFoundError(f"gallery directory not found: {args.images_dir}")
    summary = ingest_gallery(
        images_dir=args.images_dir,
        db_path=args.db,
        tile_side=args.tile_side,
        max_tiles=args.max_tiles,
        show_progress=not args.no_progress,
    )
    print(f"Ingested {summary.images} images, {summary.tiles} tiles into {args.db}")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    with cli_errors():
        run_from_args(args)


if __name__ == "__main__":
    main()

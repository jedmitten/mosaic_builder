"""Assemble a mosaic image from a match result and the tile database.

Reads the assignment produced by :mod:`mosaic_builder.matcher`, pulls every
referenced tile PNG out of DuckDB in a single bulk query, and pastes the tiles
onto an RGB canvas. Optionally blends the finished mosaic toward the original
target image so the overall composition reads more clearly from a distance.
"""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path

import duckdb
from PIL import Image

from .cli import cli_errors
from .duckdb_store import ensure_schema, get_tile_pngs_bulk, open_database
from .matcher import MatchResult, load_match_result
from .progress import iter_with_progress
from .tiler import load_image


def _decode_tiles(
    result: MatchResult,
    conn: duckdb.DuckDBPyConnection,
) -> dict[tuple[int, int], Image.Image]:
    """Fetch and decode every distinct tile referenced by ``result`` exactly once.

    A real match reuses tiles heavily (a 1024-cell grid may reference fewer than
    100 distinct tiles), so decoding per cell would repeat most of the work.
    """
    keys = list(dict.fromkeys((m.image_id, m.tile_index) for m in result.matches))
    pngs = get_tile_pngs_bulk(conn, keys, tile_side=result.tile_side)

    side = result.tile_side
    decoded: dict[tuple[int, int], Image.Image] = {}
    for key in keys:
        blob = pngs.get(key)
        if blob is None:
            raise KeyError(
                f"No tile in database for image_id={key[0]}, tile_index={key[1]}, tile_side={side}"
            )
        tile = Image.open(BytesIO(blob)).convert("RGB")
        if tile.size != (side, side):
            tile = tile.resize((side, side), Image.Resampling.LANCZOS)
        decoded[key] = tile
    return decoded


def assemble_mosaic(
    result: MatchResult,
    conn: duckdb.DuckDBPyConnection,
    *,
    show_progress: bool = False,
) -> Image.Image:
    """Paste every matched tile onto a ``(cols * tile_side, rows * tile_side)`` canvas.

    Raises ``KeyError`` naming the first ``(image_id, tile_index)`` that has no
    row in the database for ``result.tile_side``.
    """
    side = result.tile_side
    canvas = Image.new("RGB", (result.cols * side, result.rows * side))
    tiles = _decode_tiles(result, conn)

    for match in iter_with_progress(result.matches, "Rendering", show_progress):
        canvas.paste(tiles[(match.image_id, match.tile_index)], (match.col * side, match.row * side))
    return canvas


def blend_with_target(mosaic: Image.Image, target: Image.Image, alpha: float) -> Image.Image:
    """Blend ``mosaic`` toward ``target``; ``alpha`` is the weight of the target.

    ``alpha=0.0`` returns the mosaic unchanged, ``alpha=1.0`` the resized target.
    """
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"blend alpha must be between 0 and 1, got {alpha}")
    resized = target.convert("RGB").resize(mosaic.size, Image.Resampling.LANCZOS)
    return Image.blend(mosaic, resized, alpha)


def run_render(
    match_path: Path,
    db_path: Path,
    out_path: Path,
    *,
    blend: float = 0.0,
    target_path: Path | None = None,
    show_progress: bool = True,
) -> Path:
    """Render ``match_path`` against ``db_path`` and write a PNG to ``out_path``."""
    result = load_match_result(Path(match_path))

    conn = open_database(db_path)
    try:
        ensure_schema(conn)
        mosaic = assemble_mosaic(result, conn, show_progress=show_progress)
    finally:
        conn.close()

    if blend > 0.0:
        if target_path is None:
            raise ValueError("--target is required when --blend is greater than 0")
        mosaic = blend_with_target(mosaic, load_image(Path(target_path)), blend)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mosaic.save(out_path)
    return out_path


def build_parser(sub: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    """Build the argument parser.

    When ``sub`` (an argparse subparsers action) is given, the parser is
    attached to it as the ``render`` subcommand instead of standing alone.
    """
    description = "Assemble a mosaic PNG from a match result and the tile database."
    if sub is not None:
        parser = sub.add_parser("render", description=description, help=description)
    else:
        parser = argparse.ArgumentParser(description=description)

    parser.add_argument("match", type=Path, help="Path to match.json")
    parser.add_argument("--db", type=Path, default=Path("mosaic.duckdb"))
    parser.add_argument("--out", type=Path, default=Path("mosaic.png"))
    parser.add_argument(
        "--blend",
        type=float,
        default=0.0,
        help="Blend the mosaic toward the target image by this weight (0-1).",
    )
    parser.add_argument("--target", type=Path, default=None, help="Target image, required with --blend.")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress output")
    parser.set_defaults(handler=run_from_args)
    return parser


def run_from_args(args: argparse.Namespace) -> None:
    """Render from parsed arguments. Shared by this CLI and the dispatcher."""
    if not Path(args.match).exists():
        raise FileNotFoundError(f"match file not found: {args.match}")
    if not Path(args.db).exists():
        raise FileNotFoundError(f"database not found: {args.db}")
    if args.target is not None and not Path(args.target).exists():
        raise FileNotFoundError(f"target image not found: {args.target}")
    out_path = run_render(
        args.match,
        args.db,
        args.out,
        blend=args.blend,
        target_path=args.target,
        show_progress=not args.no_progress,
    )
    with Image.open(out_path) as image:
        width, height = image.size
    print(f"wrote {out_path} ({width}x{height})")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    with cli_errors():
        run_from_args(args)


if __name__ == "__main__":
    main()

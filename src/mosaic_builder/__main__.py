"""Unified command-line entry point: ``python -m mosaic_builder <subcommand>``.

Every command module owns its own argument set through ``build_parser(sub)`` and
its own behaviour through ``run_from_args(args)``, so this dispatcher only has to
collect the subparsers and call the handler that parsing selected. The one
subcommand defined here is ``mosaic``, which chains matching and rendering
without writing ``match.json`` in between.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import ingest, matcher, preview, renderer, validate
from .cli import cli_errors
from .duckdb_store import ensure_schema, open_database
from .matcher import run_match, save_match_result, summarize
from .renderer import assemble_mosaic, blend_with_target
from .tiler import load_image


def build_mosaic_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Attach the ``mosaic`` subcommand: match and render in one step."""
    description = "Match a target and render the mosaic in one step."
    parser = sub.add_parser("mosaic", description=description, help=description)
    parser.add_argument("target", type=Path)
    parser.add_argument("--db", type=Path, default=Path("mosaic.duckdb"))
    parser.add_argument("--grain", type=int, required=True, help="Cell edge length in target pixels")
    parser.add_argument("--tile-side", type=int, default=None)
    parser.add_argument("--max-reuse", type=int, default=0, help="0 means unlimited reuse")
    parser.add_argument("--min-repeat-dist", type=int, default=0, help="0 means no spacing constraint")
    parser.add_argument(
        "--blend",
        type=float,
        default=0.0,
        help="Blend the mosaic toward the target image by this weight (0-1).",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--keep-match",
        type=Path,
        default=None,
        help="Also write the match result as JSON to this path.",
    )
    parser.add_argument("--no-progress", action="store_true", help="Disable progress output")
    parser.set_defaults(handler=run_mosaic_from_args)
    return parser


def run_mosaic_from_args(args: argparse.Namespace) -> None:
    """Match then render, keeping the match result in memory."""
    target_path = Path(args.target)
    db_path = Path(args.db)
    if not target_path.exists():
        raise FileNotFoundError(f"target image not found: {target_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    if not 0.0 <= args.blend <= 1.0:
        raise ValueError(f"blend alpha must be between 0 and 1, got {args.blend}")

    show_progress = not args.no_progress
    result = run_match(
        target_path,
        db_path,
        grain=args.grain,
        tile_side=args.tile_side,
        max_reuse=args.max_reuse,
        min_repeat_dist=args.min_repeat_dist,
        show_progress=show_progress,
    )
    if args.keep_match is not None:
        save_match_result(result, args.keep_match)

    conn = open_database(db_path)
    try:
        ensure_schema(conn)
        mosaic = assemble_mosaic(result, conn, show_progress=show_progress)
    finally:
        conn.close()

    if args.blend > 0.0:
        mosaic = blend_with_target(mosaic, load_image(target_path), args.blend)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mosaic.save(out_path)
    print(f"{summarize(result)} -> {out_path} ({mosaic.width}x{mosaic.height})")


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level dispatcher parser with every subcommand attached."""
    parser = argparse.ArgumentParser(
        prog="mosaic-builder",
        description="Build photo mosaics: ingest a gallery, match a target, render the result.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    ingest.build_parser(sub)
    preview.build_parser(sub)
    matcher.build_parser(sub)
    renderer.build_parser(sub)
    build_mosaic_parser(sub)
    validate.build_parser(sub)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    with cli_errors():
        args.handler(args)


if __name__ == "__main__":
    main()

"""Read-only gallery/tile quality report — helps decide whether a gallery is
good enough before spending time on matching and rendering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .cli import cli_errors
from .duckdb_store import (
    ensure_schema,
    get_all_images,
    get_tile_lab_descriptors,
    get_tile_sides,
    open_database,
)

#: Above this many tiles, the pairwise distance matrix is computed in row
#: chunks instead of all at once, to bound peak memory.
_CHUNK_SIZE = 1024
_MAX_TILES_FULL_MATRIX = 5000

#: Coverage histogram bucket labels, in order: [0, 0.25), [0.25, 0.5),
#: [0.5, 0.75), [0.75, 1.0].
_COVERAGE_BUCKETS = ("[0, 0.25)", "[0.25, 0.5)", "[0.5, 0.75)", "[0.75, 1.0]")

_LOW_TEXTURE_N = 10


def _lab_ranges(descriptors: list[dict]) -> dict[str, list[float] | None]:
    """Return per-channel [min, max] LAB ranges, or None per channel when empty.

    LAB b* lives under the ``mean_bb`` key; ``mean_b`` is RGB blue and must
    never be used here.
    """
    if not descriptors:
        return {"L": None, "a": None, "b": None}
    l_vals = [d["mean_L"] for d in descriptors]
    a_vals = [d["mean_a"] for d in descriptors]
    b_vals = [d["mean_bb"] for d in descriptors]
    return {
        "L": [min(l_vals), max(l_vals)],
        "a": [min(a_vals), max(a_vals)],
        "b": [min(b_vals), max(b_vals)],
    }


def _mean_nearest_neighbor_delta_e(descriptors: list[dict]) -> float | None:
    """Mean, over all tiles, of each tile's distance to its nearest *other*
    tile in LAB space. Returns None when fewer than two tiles exist."""
    n = len(descriptors)
    if n < 2:
        return None

    lab = np.array(
        [[d["mean_L"], d["mean_a"], d["mean_bb"]] for d in descriptors],
        dtype=np.float64,
    )
    nearest = np.empty(n, dtype=np.float64)
    chunk_size = _CHUNK_SIZE if n > _MAX_TILES_FULL_MATRIX else n

    for start in range(0, n, chunk_size):
        end = min(start + chunk_size, n)
        chunk = lab[start:end]
        diff = chunk[:, None, :] - lab[None, :, :]
        dist = np.sqrt((diff**2).sum(-1))
        dist[np.arange(end - start), np.arange(start, end)] = np.inf
        nearest[start:end] = dist.min(axis=1)

    return float(nearest.mean())


def _coverage_histogram(descriptors: list[dict]) -> dict[str, int]:
    """Bucket tiles by coverage into [0, 0.25), [0.25, 0.5), [0.5, 0.75),
    [0.75, 1.0]. A coverage of exactly 1.0 belongs in the last bucket."""
    counts = {label: 0 for label in _COVERAGE_BUCKETS}
    for d in descriptors:
        coverage = d["coverage"]
        if coverage < 0.25:
            counts[_COVERAGE_BUCKETS[0]] += 1
        elif coverage < 0.5:
            counts[_COVERAGE_BUCKETS[1]] += 1
        elif coverage < 0.75:
            counts[_COVERAGE_BUCKETS[2]] += 1
        else:
            counts[_COVERAGE_BUCKETS[3]] += 1
    return counts


def _low_texture_tiles(descriptors: list[dict]) -> list[tuple[int, int, float]]:
    """The `_LOW_TEXTURE_N` lowest-score tiles, ascending by score."""
    ordered = sorted(descriptors, key=lambda d: d["score"])[:_LOW_TEXTURE_N]
    return [(int(d["image_id"]), int(d["tile_index"]), float(d["score"])) for d in ordered]


def gallery_report(conn, *, tile_side: int | None = None) -> dict:
    """Build a read-only gallery/tile quality report.

    Calls :func:`ensure_schema` (so a stale database fails loudly) but never
    writes tile or image rows. Safe to call on an empty database: every
    derived statistic degrades to ``None`` or an empty collection rather than
    raising.
    """
    ensure_schema(conn)

    images = get_all_images(conn)
    descriptors = get_tile_lab_descriptors(conn, tile_side=tile_side)
    tile_sides = get_tile_sides(conn)

    return {
        "image_count": len(images),
        "tile_count": len(descriptors),
        "tile_sides": tile_sides,
        "lab_ranges": _lab_ranges(descriptors),
        "mean_nearest_neighbor_delta_e": _mean_nearest_neighbor_delta_e(descriptors),
        "coverage_histogram": _coverage_histogram(descriptors),
        "low_texture_tiles": _low_texture_tiles(descriptors),
    }


def _format_report(report: dict) -> str:
    lines = [
        f"Images: {report['image_count']}",
        f"Tiles:  {report['tile_count']}",
        f"Tile sides: {report['tile_sides']}",
        "LAB ranges:",
    ]
    for channel in ("L", "a", "b"):
        lines.append(f"  {channel}: {report['lab_ranges'][channel]}")

    nn = report["mean_nearest_neighbor_delta_e"]
    nn_text = "n/a (fewer than 2 tiles)" if nn is None else f"{nn:.3f}"
    lines.append(f"Mean nearest-neighbour delta-E: {nn_text}")

    lines.append("Coverage histogram:")
    for bucket, count in report["coverage_histogram"].items():
        lines.append(f"  {bucket}: {count}")

    lines.append("Lowest-texture tiles (image_id, tile_index, score):")
    if report["low_texture_tiles"]:
        for image_id, tile_index, score in report["low_texture_tiles"]:
            lines.append(f"  ({image_id}, {tile_index}, {score:.3f})")
    else:
        lines.append("  (none)")

    return "\n".join(lines)


def build_parser(sub: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    """Build the argument parser.

    When ``sub`` (an argparse subparsers action) is given, the parser is
    attached to it as the ``validate`` subcommand instead of standing alone —
    this lets a future unified dispatcher reuse this module's argument set.
    """
    description = "Report on gallery/tile quality before matching and rendering."
    if sub is not None:
        parser = sub.add_parser("validate", description=description, help=description)
    else:
        parser = argparse.ArgumentParser(description=description)

    parser.add_argument("--db", type=Path, default=Path("mosaic.duckdb"))
    parser.add_argument(
        "--tile-side",
        type=int,
        default=None,
        help="Restrict the report to this tile side (default: all sides in the database).",
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    parser.set_defaults(handler=run_from_args)
    return parser


def run_from_args(args: argparse.Namespace) -> None:
    """Print the gallery report from parsed arguments. Shared with the dispatcher."""
    if not Path(args.db).exists():
        raise FileNotFoundError(f"database not found: {args.db}")
    conn = open_database(args.db)
    try:
        report = gallery_report(conn, tile_side=args.tile_side)
    finally:
        conn.close()

    if args.json:
        print(json.dumps(report))
    else:
        print(_format_report(report))


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    with cli_errors():
        run_from_args(args)


if __name__ == "__main__":
    main()

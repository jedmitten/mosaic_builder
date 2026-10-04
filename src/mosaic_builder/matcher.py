"""Target image analysis and greedy tile matching.

Turns a target image into a grid of per-cell LAB colour descriptors, matches
those cells against the tile descriptors held in the DuckDB store, and
persists the assignment as JSON for the renderer to consume.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .cli import cli_errors
from .duckdb_store import (
    ensure_schema,
    get_tile_lab_descriptors,
    get_tile_sides,
    open_database,
)
from .progress import iter_with_progress
from .tiler import _srgb_to_lab, load_image


@dataclass(frozen=True)
class CellDescriptor:
    row: int
    col: int
    lab: tuple[float, float, float]


@dataclass(frozen=True)
class TargetGrid:
    rows: int
    cols: int
    grain: int
    cells: list[CellDescriptor]


def analyze_target(image: Image.Image, *, grain: int) -> TargetGrid:
    """Divide a target image into a grid of cells and compute each cell's mean LAB color.

    `grain` is the edge length of one grid cell in target-image pixels.
    `rows = height // grain` and `cols = width // grain`; any remainder of
    pixels on the right and/or bottom edge (when the image dimensions are
    not exact multiples of `grain`) is dropped.

    Raises `ValueError` if the image is smaller than one cell in either
    dimension (i.e. `rows` or `cols` would be 0).
    """
    rgb_image = image.convert("RGB")
    width, height = rgb_image.size
    rows = height // grain
    cols = width // grain
    if rows == 0 or cols == 0:
        raise ValueError(
            f"Image size {width}x{height} is too small for grain={grain} (computed rows={rows}, cols={cols})"
        )

    arr = np.asarray(rgb_image, dtype=np.uint8)
    lab = _srgb_to_lab(arr)

    cropped = lab[: rows * grain, : cols * grain, :]
    blocks = cropped.reshape(rows, grain, cols, grain, 3)
    means = blocks.mean(axis=(1, 3))

    cells = [
        CellDescriptor(row=r, col=c, lab=tuple(float(v) for v in means[r, c]))
        for r in range(rows)
        for c in range(cols)
    ]

    return TargetGrid(rows=rows, cols=cols, grain=grain, cells=cells)


@dataclass(frozen=True)
class CellMatch:
    row: int
    col: int
    image_id: int
    tile_index: int
    delta_e: float


@dataclass(frozen=True)
class MatchResult:
    rows: int
    cols: int
    grain: int
    tile_side: int
    db_path: str
    matches: list[CellMatch]


#: User-facing `--diversity` dial runs 0..10; this maps it onto the reuse
#: penalty in Delta-E units per prior placement. At 10 a tile already used
#: once is treated as ~6 Delta-E worse than it measures, which is half the
#: "looks off" threshold of ~12 — strong pressure without ignoring colour.
_DIVERSITY_SCALE = 0.6

#: Default dial position. Measured on the 1440-tile gallery against the urinal
#: target at grain 25: mean Delta-E 5.34 (well inside the ~12 "looks off"
#: threshold), 587 distinct tiles, no tile placed more than 4 times. At 0 a
#: single tile was used 138 times out of 900 cells. See the README table.
_DEFAULT_DIVERSITY = 3.0

#: Chebyshev radius within which a repeat is considered "nearby" and charged
#: extra. Beyond this, only the global use count applies.
_LOCAL_RADIUS = 4

#: How much more a repeat immediately adjacent costs than a generic reuse.
#: Falls off linearly to zero at `_LOCAL_RADIUS`.
_LOCAL_STRENGTH = 4.0


def diversity_weight(diversity: float) -> float:
    """Map the 0..10 `--diversity` dial onto a Delta-E-per-reuse penalty."""
    return max(0.0, float(diversity)) * _DIVERSITY_SCALE


def _nearby_placements(
    placed: dict[tuple[int, int], int], cell: CellDescriptor, radius: int
) -> list[tuple[tuple[int, int], int]]:
    """Already-placed cells within Chebyshev `radius` of `cell`.

    Scans the neighbourhood rather than every prior placement, so the cost per
    cell stays constant as the mosaic grows.
    """
    found = []
    for row in range(cell.row - radius, cell.row + 1):
        for col in range(cell.col - radius, cell.col + radius + 1):
            tile_idx = placed.get((row, col))
            if tile_idx is not None:
                found.append(((row, col), tile_idx))
    return found


def _distances(cells: np.ndarray, tiles: np.ndarray) -> np.ndarray:
    """Euclidean (CIE76) distance matrix between cell and tile LAB vectors."""
    return np.sqrt(((cells[:, None, :] - tiles[None, :, :]) ** 2).sum(-1))


def match_grid(
    grid: TargetGrid,
    descriptors: list[dict],
    *,
    tile_side: int,
    db_path: str,
    diversity: float = _DEFAULT_DIVERSITY,
    show_progress: bool = False,
) -> MatchResult:
    """Assign a tile to every cell of `grid`, trading colour fidelity for variety.

    `descriptors` is the list returned by `get_tile_lab_descriptors`; LAB is
    read from the keys `mean_L`, `mean_a` and `mean_bb` (note that `mean_b` is
    RGB blue, not LAB b*).

    Cells are walked in row-major order. Each tile is costed as::

        cost = delta_e + diversity_weight(diversity) * penalty

    where ``penalty`` is how many times the tile has already been placed
    *relative to its fair share* (``cells / tiles``), plus an extra charge for
    placements within `_LOCAL_RADIUS` cells of this one that falls off with
    distance. The cheapest tile wins. A heavily reused tile can therefore still
    be chosen when it is a markedly better colour match, which is the point:
    `diversity` expresses a preference, not a constraint.

    Scaling by fair share is what keeps a dial position meaning the same thing
    across galleries. With fewer tiles than cells, repeats are unavoidable, and
    charging for them from the first repeat would drown out colour distance.

    `diversity` runs 0..10. At 0 this is plain nearest-colour matching. Higher
    values buy variety at the cost of mean Delta-E; see the README's tradeoff
    table. There is no unsatisfiable-constraint case to fall back from, so this
    never silently ignores the setting.
    """
    if not descriptors:
        raise ValueError("No tiles in database")

    keys = [(int(d["image_id"]), int(d["tile_index"])) for d in descriptors]
    tiles = np.array(
        [[float(d["mean_L"]), float(d["mean_a"]), float(d["mean_bb"])] for d in descriptors],
        dtype=np.float64,
    )
    cells = np.array([cell.lab for cell in grid.cells], dtype=np.float64)

    n_cells = cells.shape[0]
    n_tiles = tiles.shape[0]
    chunk_size = 1024 if n_cells * n_tiles > 20_000_000 else n_cells

    weight = diversity_weight(diversity)
    #: How often each tile must be placed if usage were spread perfectly. When
    #: cells outnumber tiles this is large, and reuse is unavoidable — charging
    #: for it from the first repeat would swamp colour distance and make the
    #: choice effectively random. Measuring usage relative to this keeps a dial
    #: position meaning the same thing on a 9-tile and a 14000-tile gallery.
    fair_share = max(n_cells / n_tiles, 1e-9)
    uses = np.zeros(n_tiles, dtype=np.float64)
    #: Tile index placed at each (row, col), for the local-repeat lookup.
    placed: dict[tuple[int, int], int] = {}
    matches: list[CellMatch] = []

    block: np.ndarray | None = None
    block_start = 0
    for i in iter_with_progress(range(n_cells), "Matching cells", show_progress):
        if block is None or i >= block_start + block.shape[0]:
            block_start = i
            block = _distances(cells[i : i + chunk_size], tiles)
        dists = block[i - block_start]
        cell = grid.cells[i]

        if weight <= 0.0:
            chosen = int(np.argmin(dists))
        else:
            penalty = uses / fair_share
            for (row, col), tile_idx in _nearby_placements(placed, cell, _LOCAL_RADIUS):
                distance = max(abs(row - cell.row), abs(col - cell.col))
                falloff = (_LOCAL_RADIUS - distance + 1) / (_LOCAL_RADIUS + 1)
                # Take the closest prior placement rather than summing them.
                # Summing stacks up when few tiles are available, swamping
                # colour distance; what actually reads badly is one repeat
                # sitting near this cell, not several scattered in range.
                local = _LOCAL_STRENGTH * falloff
                penalty[tile_idx] = max(penalty[tile_idx], uses[tile_idx] / fair_share + local)
            chosen = int(np.argmin(dists + weight * penalty))

        uses[chosen] += 1.0
        placed[(cell.row, cell.col)] = chosen
        key = keys[chosen]
        matches.append(
            CellMatch(
                row=cell.row,
                col=cell.col,
                image_id=key[0],
                tile_index=key[1],
                delta_e=float(dists[chosen]),
            )
        )

    return MatchResult(
        rows=grid.rows,
        cols=grid.cols,
        grain=grid.grain,
        tile_side=int(tile_side),
        db_path=str(db_path),
        matches=matches,
    )


def save_match_result(result: MatchResult, path: Path) -> None:
    """Write `result` to `path` as JSON."""
    payload = {
        "rows": result.rows,
        "cols": result.cols,
        "grain": result.grain,
        "tile_side": result.tile_side,
        "db_path": result.db_path,
        "matches": [
            {
                "row": m.row,
                "col": m.col,
                "image_id": m.image_id,
                "tile_index": m.tile_index,
                "delta_e": m.delta_e,
            }
            for m in result.matches
        ],
    }
    Path(path).write_text(json.dumps(payload, indent=2))


def load_match_result(path: Path) -> MatchResult:
    """Read a `MatchResult` back from the JSON written by `save_match_result`."""
    payload = json.loads(Path(path).read_text())
    matches = [
        CellMatch(
            row=int(m["row"]),
            col=int(m["col"]),
            image_id=int(m["image_id"]),
            tile_index=int(m["tile_index"]),
            delta_e=float(m["delta_e"]),
        )
        for m in payload["matches"]
    ]
    return MatchResult(
        rows=int(payload["rows"]),
        cols=int(payload["cols"]),
        grain=int(payload["grain"]),
        tile_side=int(payload["tile_side"]),
        db_path=str(payload["db_path"]),
        matches=matches,
    )


def run_match(
    target_path: Path,
    db_path: Path,
    *,
    grain: int,
    tile_side: int | None = None,
    diversity: float = _DEFAULT_DIVERSITY,
    show_progress: bool = True,
) -> MatchResult:
    """Analyse `target_path` and match it against the tiles in `db_path`."""
    image = load_image(Path(target_path))
    conn = open_database(db_path)
    try:
        ensure_schema(conn)
        if tile_side is None:
            sides = get_tile_sides(conn)
            if not sides:
                raise ValueError("No tiles in database")
            if len(sides) > 1:
                raise ValueError(
                    f"Database holds multiple tile sides ({', '.join(str(s) for s in sides)}); "
                    "pass --tile-side to choose one"
                )
            tile_side = sides[0]
        grid = analyze_target(image, grain=grain)
        descriptors = get_tile_lab_descriptors(conn, tile_side=tile_side)
    finally:
        conn.close()

    return match_grid(
        grid,
        descriptors,
        tile_side=tile_side,
        db_path=str(db_path),
        diversity=diversity,
        show_progress=show_progress,
    )


def build_parser(sub: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    """Build this module's parser, standalone or attached to a subparsers action."""
    description = "Match a target image against the tile database."
    parser = (
        sub.add_parser("match", description=description, help=description)
        if sub is not None
        else argparse.ArgumentParser(description=description)
    )
    parser.add_argument("target", type=Path)
    parser.add_argument("--db", type=Path, default=Path("mosaic.duckdb"))
    parser.add_argument("--grain", type=int, required=True, help="Cell edge length in target pixels")
    parser.add_argument("--tile-side", type=int, default=None)
    parser.add_argument(
        "--diversity",
        type=float,
        default=3.0,
        help="0-10: how much to favour tile variety over exact colour match (0 = pure match)",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-progress", action="store_true", help="Disable progress output")
    parser.set_defaults(handler=run_from_args)
    return parser


def run_from_args(args: argparse.Namespace) -> None:
    """Run matching from parsed arguments. Shared by this CLI and the dispatcher."""
    if not Path(args.target).exists():
        raise FileNotFoundError(f"target image not found: {args.target}")
    if not Path(args.db).exists():
        raise FileNotFoundError(f"database not found: {args.db}")
    result = run_match(
        args.target,
        args.db,
        grain=args.grain,
        tile_side=args.tile_side,
        diversity=args.diversity,
        show_progress=not args.no_progress,
    )
    save_match_result(result, args.out)
    print(summarize(result), "->", args.out)


def summarize(result: MatchResult) -> str:
    """One-line human summary of a match result."""
    mean_delta_e = sum(m.delta_e for m in result.matches) / len(result.matches) if result.matches else 0.0
    distinct = len({(m.image_id, m.tile_index) for m in result.matches})
    return f"rows={result.rows} cols={result.cols} mean_delta_e={mean_delta_e:.3f} distinct_tiles={distinct}"


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    with cli_errors():
        run_from_args(args)


if __name__ == "__main__":
    main()

# mosaic-builder

Build photo mosaics from your own gallery, backed by DuckDB.

A gallery of photos is sliced into texture-scored square "character tiles". Each tile is normalized
to a uniform square and stored in DuckDB with its average color in both RGB and CIE-LAB. A target
image is then divided into a grid, each cell is matched to the closest tile by perceptual color
distance, and the chosen tiles are assembled into the finished mosaic.

## Install

```bash
uv sync
uv run pytest -q
```

## Quickstart

Three commands take you from a folder of photos to a mosaic.

```bash
# 1. Ingest a gallery into the database
uv run mosaic-builder ingest gallery --db mosaic.duckdb --tile-side 64

# 2. Check whether the gallery is varied enough to make a good mosaic
uv run mosaic-builder validate --db mosaic.duckdb

# 3. Match a target and render the mosaic in one step
uv run mosaic-builder mosaic path/to/target.png --db mosaic.duckdb \
    --grain 32 --max-reuse 4 --min-repeat-dist 3 --out mosaic.png

open mosaic.png
```

Every subcommand also runs as a module, for example `python -m mosaic_builder.ingest`.

## grain versus tile-side

These two numbers are easy to confuse and control different things.

**`--tile-side`** is how many pixels wide each stored tile is. It is fixed when you ingest, and it
sets the resolution of the mosaic's building blocks. **`--grain`** is how many pixels of the
*target* image one grid cell covers. It is chosen at match time and it decides how many cells the
mosaic has: a 1024-pixel-wide target at `--grain 32` gives 32 columns.

The output size is the grid size times the tile side. A 32 by 32 grid of 64-pixel tiles produces a
2048 by 2048 image. Smaller grain means more cells, a closer likeness, and a bigger output.

## Commands

### ingest

| Flag | Default | Meaning |
|---|---|---|
| `images_dir` | required | Directory of source photos |
| `--db` | `mosaic.duckdb` | Database to write |
| `--tile-side` | `64` | Pixel edge length every tile is resized to |
| `--max-tiles` | `3` | Maximum tiles extracted per photo |
| `--no-progress` | off | Suppress the progress bar |

### validate

| Flag | Default | Meaning |
|---|---|---|
| `--db` | `mosaic.duckdb` | Database to read |
| `--tile-side` | all | Restrict the report to one tile side |
| `--json` | off | Emit JSON instead of a table |

Reports tile counts, color ranges, the coverage histogram, the lowest-texture tiles, and the mean
nearest-neighbor color distance. A low nearest-neighbor value means many near-duplicate tiles.

### mosaic

| Flag | Default | Meaning |
|---|---|---|
| `target` | required | Image to reproduce |
| `--db` | `mosaic.duckdb` | Database to read |
| `--grain` | required | Target pixels per grid cell |
| `--tile-side` | auto | Which stored tile side to use |
| `--max-reuse` | `0` | Times one tile may appear, 0 for unlimited |
| `--min-repeat-dist` | `0` | Cells a tile must stay apart from itself, 0 for no limit |
| `--blend` | `0.0` | Blend the result toward the target, 0 to 1 |
| `--out` | required | Output PNG |
| `--keep-match` | off | Also write the assignments as JSON |
| `--no-progress` | off | Suppress the progress bar |

### match and render

`mosaic` is `match` followed by `render`. Run them separately when you want to inspect or hand-edit
the assignments, or re-render at a different `--blend` without matching again.

```bash
uv run mosaic-builder match target.png --db mosaic.duckdb --grain 32 --out match.json
uv run mosaic-builder render match.json --db mosaic.duckdb --out mosaic.png
```

### preview

```bash
uv run mosaic-builder preview --db mosaic.duckdb --out preview.html --first-n 25
```

Renders an HTML page of stored tiles so you can audit extraction quality. Use `--first-n` or
`--random-n` to sample; the full gallery produces a very large file.

## Tuning quality versus variety

Unconstrained matching picks the single closest tile for every cell, so a handful of tiles repeat
across large flat areas. `--max-reuse` and `--min-repeat-dist` force variety at the cost of color
accuracy. Measured on a 480-photo gallery at a 32 by 32 grid:

| Settings | Mean color error | Distinct tiles used |
|---|---|---|
| unconstrained | 4.88 | 95 |
| `--min-repeat-dist 5` | 8.12 | 193 |
| `--max-reuse 4 --min-repeat-dist 3` | 12.00 | 314 |
| `--max-reuse 2 --min-repeat-dist 2` | 13.92 | 536 |
| `--max-reuse 1` | 17.87 | 1024 |

Color errors past roughly 12 start to read as visibly wrong, so the third row is about as far as
that gallery can be pushed. Run `validate` on your own gallery to see where its limit sits.

## Databases and schema

One database file holds tiles at a single `--tile-side`. To try a different size, write to a new
file or delete the existing one and re-ingest.

The schema is versioned. Opening a database written by an older version fails immediately with a
message telling you to delete it and re-ingest. There are no migrations, because re-ingesting a
480-photo gallery takes under two minutes.

## Repository layout

- `CONTEXT.md` records the design intent, validated assumptions, and measured gallery statistics.
- `PLAN.md` is the task-by-task execution plan, including work not yet done.
- `notebooks/visual_demo.ipynb` walks through every stage visually and runs without a personal
  gallery, generating synthetic images when none is present.

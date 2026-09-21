# mosaic-builder

A Python toolkit for building photo mosaics backed by DuckDB. A gallery of photos is sliced into
texture-scored square "character tiles", each tile is normalized to a uniform side length, and its
color descriptors (mean RGB and mean CIE-LAB) are stored in DuckDB alongside the tile PNG. Later
stages match those tiles against a target image and render the mosaic.

## Current State

- **Ingestion** — `ingest.py` extracts character tiles, resizes them to a uniform square, computes
  RGB and LAB descriptors, and writes them to DuckDB inside a per-image transaction.
- **Storage** — `duckdb_store.py` owns the schema, a versioned schema guard, read helpers, and
  transactional upserts.
- **Preview** — `preview.py` renders an HTML gallery straight from the database so tile coverage
  and quality can be audited without re-ingesting.
- **Matching and rendering** — not built yet. See `PLAN.md` for the task-by-task plan.

## Getting Started

```bash
uv sync
uv run pytest tests/ -q
```

## Quickstart

```bash
# 1. Ingest a gallery directory into the database
uv run python -m mosaic_builder.ingest gallery --db mosaic.duckdb --tile-side 64

# 2. Render an HTML preview of what was stored
uv run python -m mosaic_builder.preview --db mosaic.duckdb --out preview.html --first-n 25

open preview.html
```

### Ingest flags

| Flag | Default | Meaning |
|---|---|---|
| `images_dir` (positional) | required | Directory of source photos |
| `--db` | `mosaic.duckdb` | DuckDB file to write |
| `--tile-side` | `64` | Edge length in pixels every tile is resized to |
| `--max-tiles` | `3` | Maximum character tiles extracted per photo |
| `--no-progress` | off | Suppress the progress bar (use in CI) |

### Preview flags

| Flag | Default | Meaning |
|---|---|---|
| `--db` | `mosaic.duckdb` | DuckDB file to read |
| `--out` | `preview.html` | Output HTML path |
| `--first-n` | all | Show only the first N images |
| `--random-n` | all | Show a random N images (mutually exclusive with `--first-n`) |

## Notes

- One database file holds tiles at a single `--tile-side`. To experiment with a different side
  length, delete the `.duckdb` file and re-ingest.
- The schema is versioned. Opening a database written by an older version raises a clear error
  telling you to delete and re-ingest; there are no migrations.
- `CONTEXT.md` captures the guiding goals and assumptions. `PLAN.md` is the execution plan for the
  remaining work.

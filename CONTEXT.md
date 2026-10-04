# Project Context

## Vision

- Create mosaics that reassemble a target image out of source photos, treating each source-derived tile as a "pixel" that carries texture and color from the original photograph.
- Prioritize creative control: ingest curated galleries, generate multiple representative tiles per photo, and let matching/rendering knobs expose artistic trade-offs (grain, diversity, reuse limits).
- Standardize storage on DuckDB for both ingestion metadata and tile features to avoid backend sprawl.

## Architecture

### Modules

- **`duckdb_store.py`** — Schema, schema versioning, read helpers, and transactional upserts. The database stamps `SCHEMA_VERSION` into a `schema_meta` table; `ensure_schema` raises `SchemaVersionError` for a legacy, older, or newer file. There are no migrations. Deletion of an image's tiles is done manually inside `upsert_image`, not by a foreign-key cascade.
- **`tiler.py`** — Image loading (EXIF-aware), character tile extraction (texture-scored square crops), resizing, mean RGB, mean LAB, and CIE76 `delta_e`.
- **`ingest.py`** — Gallery ingestion into DuckDB. Per-image transactions with rollback on failure. Returns `IngestSummary`.
- **`preview.py`** — HTML preview generation. Reads from the database; never re-ingests.
- **`matcher.py`** — Target analysis (`analyze_target` builds a grid of per-cell LAB descriptors) and assignment (`match_grid`) minimising `delta_e + weight x reuse penalty`, where `--diversity` sets the weight. Results serialize to `match.json`.
- **`renderer.py`** — Mosaic assembly from a match result, with optional alpha blending toward the target.
- **`validate.py`** — Read-only gallery quality report: LAB ranges, nearest-neighbour diversity, coverage histogram, lowest-texture tiles.
- **`progress.py`** — The single text progress-bar helper shared by ingest, match, and render.
- **`cli.py`** — `cli_errors()`, which turns expected user errors into a one-line message and exit status 1 while letting real bugs keep their traceback.
- **`__main__.py`** — Unified subcommand dispatcher.

Every command module exposes the same shape: `build_parser(sub=None)`, `run_from_args(args)`, and `main(argv=None)`. That is what lets each module run standalone and be attached to the dispatcher without duplicated argument definitions.

### Data Flow

```
Gallery dir → ingest.py → DuckDB (images + tiles) → preview.py  → preview.html
                                 │              └─→ validate.py → quality report
                                 │
Target image → matcher.py (analyze_target → match_grid) → MatchResult → match.json
                                 │
                       renderer.py (assemble_mosaic [+ blend]) → mosaic.png
```

## Validated Assumptions / Lessons

1. **Character Tiles Matter**
   Extracting up to three maximal square crops per photo (scoring by texture/contrast) preserves the photographed "character" better than a single average crop. Each tile is resized uniformly afterward.

2. **Perceptual Metrics for Fast-Fail**
   Delta-E in LAB is the matching distance. Tiles drifting beyond roughly 12 Delta-E from their target typically feel off. Supporting per-tile metrics help diagnose why: `coverage`, texture `score`, `color_contrast` and `periodicity` are measured at ingest and stored; the composite fixture likelihood is derived from them on read. README's "What the tile scores mean" explains each in plain terms. (Entropy and colorfulness were considered as supporting metrics but never implemented.)

3. **Grain & Diversity Controls**
   Greedy raster-order matching plus a continuous `--diversity` dial are enough for early experiments. The dial is a soft cost, not a constraint: a reused tile still wins when it is a markedly better colour match, and the penalty is scaled by each tile's fair share (`cells / tiles`) so that forced repeats on a small gallery do not swamp colour distance. More sophisticated solvers can wait until real failures appear.

4. **Tooling over Ad Hoc Scripts**
   Standalone analyzers made it easy to score galleries before committing to large ingests. `validate` is the CLI form of that idea.

5. **Decoupled Ingest and Preview**
   Ingestion writes to the database only. Preview and validation read from it. This allows previewing without re-ingesting and ingesting without preview cost.

6. **Schema Versioning Beats Migrations**
   An unversioned database silently passed schema creation and then failed with a raw binder error on the first LAB query. Stamping a version and failing loudly with "delete and re-ingest" is cheaper than migration code, because a full re-ingest of 480 photos takes under two minutes.

## Measured Characteristics (480 photos, 1440 tiles, tile_side 64)

- Mean nearest-neighbour Delta-E between tiles is **1.06**, or **1.46** ignoring tiles from the same photo. Only **125 of 1440** tiles sit more than 3 Delta-E from their nearest neighbour in a different photo. The gallery is tightly clustered in color space.
- Consequences: substitutes are plentiful, so diversity is cheap to buy — which is exactly why the soft `--diversity` penalty beats the hard reuse/spacing caps it replaced. Mean color alone is nearly exhausted as a discriminator.
- The quality-versus-variety tradeoff, measured on the urinal target at grain 25 (30x30 grid, 900 cells):

  | `--diversity` | Mean Delta-E | Distinct tiles | Most-reused tile |
  |---|---|---|---|
  | 0 | 3.24 | 76 | 138 cells |
  | 1 | 4.82 | 467 | 6 |
  | 3 (default) | 5.77 | 699 | 3 |
  | 5 | 6.40 | 815 | 2 |
  | 10 | 7.04 | 889 | 2 |

  The old hard caps needed a mean Delta-E of 13.92 — past the 12 rule of thumb — to reach 536 distinct tiles; the soft penalty reaches 699 at 5.77, because it only swaps where a near-equal tile exists instead of forcing every cell past its best match. Re-measure with `python -m mosaic_builder validate` after any change to tile extraction.

## Superseded Work (recoverable, not forgotten)

On 2026-10-04 `main` was resolved in favour of this tree (PR #4, merged with the `ours` strategy). `main` had diverged into a *different codebase* rather than a variant of this one — `mosaic_builder/` holding `index/`, `pipeline/`, `stores/` and `config.py`, against `src/mosaic_builder/` with flat modules here. Only `README.md` and `pyproject.toml` actually conflicted; everything else sat at different paths, so an ordinary merge would have produced two directories claiming the same import name rather than a working tree.

Dropped from the mainline, intact at commit `6d7042a` and on the `move-to-grid` branch:

- **Grid tiling** (PR #3) — grids in tiling, with matching schema and CLI changes.
- **Approximate nearest-neighbour index** — `index/` with brute-force, kd-tree, HNSW and FAISS backends behind a factory.
- **A different layering** — `config.py`, `pipeline/`, `stores/sql_store.py` separating ingest and storage differently than the flat modules here.

Why this matters later: matching here is brute-force LAB distance against every tile, which is comfortable at 1440 tiles and would not be at ten times that. If gallery size becomes the constraint, recover the index work above rather than rebuilding it. Nothing in the current architecture precludes it — `match_grid` already receives a plain list of descriptors and could be handed an index instead.

## Non-Goals (for now)

- No alternative databases. DuckDB is the single source of truth.
- No schema migrations. Delete the file and re-ingest.
- No GUI editor; CLI plus Python API.
- No plugin architecture.

## Next Build Steps

1. **Sub-cell descriptors** — store a 2x2 or 3x3 LAB grid per tile and per cell and match on the concatenated vector. Given the clustering measured above, this is the biggest remaining quality lever.
2. **Tile augmentation** — ingest flipped and rotated variants to enlarge a small gallery.
3. **Render-time tinting** — nudge each tile toward its cell's mean color to hide residual color error.
4. **Proper multi-tile-side support** — today one database holds one tile side; the write path would need to delete per `(image_id, tile_side)` rather than per image.
5. **Replace the gallery symlink** — a configurable gallery path so the notebook and README do not depend on one machine's layout.
6. **Approximate nearest-neighbour matching** — only once brute-force LAB distance stops being fast enough. Recover the `index/` subsystem described under Superseded Work instead of writing a new one.

Keep this file up to date as the project evolves.

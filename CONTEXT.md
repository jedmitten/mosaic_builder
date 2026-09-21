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
- **`matcher.py`** — Target analysis (`analyze_target` builds a grid of per-cell LAB descriptors) and greedy assignment (`match_grid`) under reuse and spacing constraints. Results serialize to `match.json`.
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
   Delta-E in LAB is the matching distance. Tiles drifting beyond roughly 12 Delta-E from their target typically feel off. Supporting metrics (entropy, colorfulness, coverage) help diagnose why.

3. **Grain & Diversity Controls**
   Greedy raster-order matching plus grid knobs (grain, min-repeat distance, max reuse) are enough for early experiments. More sophisticated solvers can wait until real failures appear.

4. **Tooling over Ad Hoc Scripts**
   Standalone analyzers made it easy to score galleries before committing to large ingests. `validate` is the CLI form of that idea.

5. **Decoupled Ingest and Preview**
   Ingestion writes to the database only. Preview and validation read from it. This allows previewing without re-ingesting and ingesting without preview cost.

6. **Schema Versioning Beats Migrations**
   An unversioned database silently passed schema creation and then failed with a raw binder error on the first LAB query. Stamping a version and failing loudly with "delete and re-ingest" is cheaper than migration code, because a full re-ingest of 480 photos takes under two minutes.

## Measured Characteristics (480 photos, 1440 tiles, tile_side 64)

- Mean nearest-neighbour Delta-E between tiles is **1.06**, or **1.46** ignoring tiles from the same photo. Only **125 of 1440** tiles sit more than 3 Delta-E from their nearest neighbour in a different photo. The gallery is tightly clustered in color space.
- Consequences: reuse and spacing constraints are cheap to satisfy because substitutes are plentiful, and mean color alone is nearly exhausted as a discriminator.
- The quality-versus-variety tradeoff on a 32x32 grid:

  | Settings | Mean Delta-E | Distinct tiles |
  |---|---|---|
  | unconstrained | 4.88 | 95 |
  | `--min-repeat-dist 5` | 8.12 | 193 |
  | `--max-reuse 4 --min-repeat-dist 3` | 12.00 | 314 |
  | `--max-reuse 2 --min-repeat-dist 2` | 13.92 | 536 |
  | `--max-reuse 1` | 17.87 | 1024 |

  Pushing past roughly 300 distinct tiles crosses the 12 Delta-E rule of thumb. Re-measure with `python -m mosaic_builder validate` after any change to tile extraction.

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

Keep this file up to date as the project evolves.

# Project Context

## Vision

- Create mosaics that reassemble a target image out of source photos, treating each source-derived tile as a "pixel" that carries texture and color from the original photograph.
- Prioritize creative control: ingest curated galleries, generate multiple representative tiles per photo, and let matching/rendering knobs expose artistic trade-offs (grain, diversity, reuse limits).
- Standardize storage on DuckDB for both ingestion metadata and tile features to avoid backend sprawl.

## Architecture

### Modules

- **`duckdb_store.py`** — Schema (with SEQUENCE-based IDs, CASCADE deletes), read helpers (`get_all_images`, `get_tiles_for_image`, `get_all_tiles`, `get_tile_png`), and transactional upsert helpers (`upsert_image`, `upsert_tiles`).
- **`tiler.py`** — Image loading (EXIF-aware), character tile extraction (texture-scored square crops), resizing, mean RGB computation. No duplicate EXIF transpose.
- **`ingest.py`** — Gallery ingestion into DuckDB. Decoupled from preview. Per-image transactions with rollback on failure. Returns `IngestSummary`. CLI via `python -m mosaic_builder.ingest`.
- **`preview.py`** — HTML preview generation. Reads from DB (no re-ingestion). CLI via `python -m mosaic_builder.preview`.

### Data Flow

```
Gallery dir → ingest.py → DuckDB (images + tiles tables)
                                    ↓
                              preview.py → HTML file
```

## Validated Assumptions / Lessons

1. **Character Tiles Matter**
   Extracting up to three maximal square crops per photo (scoring by texture/contrast) preserves the photographed "character" better than a single average crop. Each tile should be resized uniformly afterward.

2. **Perceptual Metrics for Fast-Fail**
   Computing average Delta-E (Lab) between a tile and the photo's global crop is an effective sanity check—tiles drifting beyond ~12 ΔE typically feel off. Supporting metrics (entropy, colorfulness, coverage) help diagnose why.

3. **Grain & Diversity Controls**
   Greedy matching plus grid-based knobs (grain stride/offset, min-repeat distance, optional max reuse) are enough for early-stage experiments. More sophisticated solvers can wait until real failures appear.

4. **Tooling over Ad Hoc Scripts**
   Standalone analyzers (e.g., `validate_tiles`) made it easy to score galleries before committing to large ingests. Keep such tools lightweight and CLI-friendly.

5. **Decoupled Ingest and Preview**
   Ingestion writes to DB only (no base64 encoding overhead). Preview reads from DB. This allows previewing without re-ingesting and ingesting without preview cost.

## Non-Goals (for now)

- No alternative databases—DuckDB is the single source of truth.
- No GUI editor; focus on CLI + Python API.
- No sprawling plugin architecture until basic ingest → match → render path is solid.

## Next Build Steps

1. Add LAB descriptors to the tile feature set for perceptual matching.
2. Implement target image analysis and grid-based matching.
3. Build the rendering pipeline (mosaic assembly from matched tiles).
4. Add a validation CLI that queries DuckDB to score gallery quality.

Keep this file up to date as the project evolves.

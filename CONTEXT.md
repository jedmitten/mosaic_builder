# Project Context (Rebuild Primer)

This file captures the intent and validated assumptions from the earlier mosaic-builder spike so we can safely delete the old codebase and rebuild with purpose.

## Vision

- Create mosaics that reassemble a target image out of source photos, treating each source-derived tile as a “pixel” that carries texture and color from the original photograph.
- Prioritize creative control: ingest curated galleries, generate multiple representative tiles per photo, and let matching/rendering knobs expose artistic trade-offs (grain, diversity, reuse limits).
- Standardize storage on DuckDB for both ingestion metadata and tile features to avoid backend sprawl.

## Validated Assumptions / Lessons

1. **Character Tiles Matter**  
   Extracting up to three maximal square crops per photo (scoring by texture/contrast) preserves the photographed “character” better than a single average crop. Each tile should be resized uniformly afterward.

2. **Perceptual Metrics for Fast-Fail**  
   Computing average Delta-E (Lab) between a tile and the photo’s global crop is an effective sanity check—tiles drifting beyond ~12 ΔE typically feel off. Supporting metrics (entropy, colorfulness, coverage) help diagnose why.

3. **Grain & Diversity Controls**  
   Greedy matching plus grid-based knobs (grain stride/offset, min-repeat distance, optional max reuse) are enough for early-stage experiments. More sophisticated solvers can wait until real failures appear.

4. **Tooling over Ad Hoc Scripts**  
   Standalone analyzers (e.g., `validate_tiles`) made it easy to score galleries before committing to large ingests. Keep such tools lightweight and CLI-friendly.

## Non-Goals (for now)

- No alternative databases—DuckDB is the single source of truth.
- No GUI editor; focus on CLI + Python API.
- No sprawling plugin architecture until basic ingest → match → render path is solid.

## Next Build Steps

1. Scaffold a minimal uv-managed package (pyproject, src package, tests).
2. Reintroduce a DuckDB-focused ingestion module that:
   - Enumerates gallery photos, stores metadata + character tiles.
   - Persists tile descriptors (LAB + future embeddings) directly into DuckDB tables.
3. Add a validation CLI (revive `validate_tiles`) that queries DuckDB instead of walking raw files.
4. Layer on matching/rendering once ingestion fidelity is satisfactory.

Keep this file up to date as the rebuild evolves so future resets remain painless.

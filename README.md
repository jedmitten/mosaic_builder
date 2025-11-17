# mosaic-builder

A Python toolkit for building photo mosaics backed by DuckDB. The current codebase provides the foundational ingestion and inspection utilities used to slice galleries into “character tiles”, store their metrics in DuckDB, and review the results in a lightweight HTML preview. During ingestion, every crop is resized to a uniform square (your chosen `--tile-side`) before descriptors/PNGs are stored so later stages—matching, indexing, rendering—operate on consistent tile dimensions without additional transforms.

## Current State

- Minimal `pyproject.toml` + `uv.lock` for dependency management.
- No source code yet—future modules will be rebuilt from scratch.
- `CONTEXT.md` captures the legacy goals, validated assumptions, and next steps for the new implementation.

## Getting Started

```bash
uv sync
uv run python -m unittest discover -s tests
```

## Quickstart

```bash
# Generate preview.html from images in ./gallery
uv run python -m mosaic_builder.preview gallery --db mosaic.duckdb --out preview.html --tile-side 64
# Add --no-progress for quiet output (e.g., CI)
# uv run python -m mosaic_builder.preview gallery --no-progress
open preview.html  # or use your browser
```

Use `CONTEXT.md` to understand the intended direction before adding new packages or modules.

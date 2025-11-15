# mosaic-builder (reset)

This repository has been pared back to a fresh uv-managed Python project so the mosaic engine can be redesigned around a DuckDB-only pipeline. All previous source, tests, and tools have been removed on purpose.

## Current State

- Minimal `pyproject.toml` + `uv.lock` for dependency management.
- No source code yet—future modules will be rebuilt from scratch.
- `CONTEXT.md` captures the legacy goals, validated assumptions, and next steps for the new implementation.

## Getting Started

```bash
uv sync
uv run python -V
```

Use `CONTEXT.md` to understand the intended direction before adding new packages or modules.

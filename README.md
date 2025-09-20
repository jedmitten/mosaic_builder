# mosaic-builder

**mosaic-builder** is a Python toolkit for creating **photo mosaics**: reassembling a target image out of thousands of source tiles. It’s built for creative and artistic workflows where you want flexible control over how images are ingested, indexed, matched, and rendered.

---

## Goals

* Provide a **reusable library** for tiling, indexing, and querying photos.
* Support ingesting large photo collections into efficient local stores (DuckDB, SQLite).
* Allow flexible nearest-neighbor backends (KD-Tree, HNSW, Faiss).
* Act as the **engine** behind art projects (e.g. *Views from the Urinal*).
* Stay **backend-agnostic** with clear interfaces between storage, indexing, and rendering.

---

## Non-Goals

* Not a full GUI mosaic editor.
* Not a replacement for photo cataloging software (e.g. Lightroom).
* Not yet optimized for billion-tile distributed datasets (though the design leaves room).
* Not a general-purpose image processing toolkit — the focus is narrowly on mosaics.

---

## Installation

```bash
git clone https://github.com/jedmitten/mosaic_builder.git
cd mosaic_builder
uv sync   # or: pip install -e .
```

Optional extras:

```bash
uv sync --extra analytics   # DuckDB + Pandas support
uv sync --extra debug       # matplotlib debug visuals
```

---

## Command-Line Usage

```bash
# Ingest source photos into a DuckDB store
mosaic-builder ingest --images-dir gallery --store duckdb:///mosaic.duckdb

# Build a KD-Tree index of tiles
mosaic-builder build-index --store duckdb:///mosaic.duckdb --index tiles_kdtree.pkl

# Generate a mosaic from a target image
mosaic-builder build-mosaic --target urinal.jpg --index tiles_kdtree.pkl --out mosaic.png
```

---

## Python API

```python
from mosaic_builder.pipeline import ingest_dir
from mosaic_builder.stores.factory import open_store

store = open_store("duckdb:///mosaic.duckdb")
ingest_dir("duckdb:///mosaic.duckdb", "gallery", tile_w=24, tile_h=24)
```

---

## Matching & Grain

Tile placement is handled by `greedy_match`. The `grain` parameter controls the **grid stride and offset**:

* **Coarse (`grain >= 1.0`)**

  * stride = `tile_side`
  * offset = `tile_side // 2` (misaligned)
  * Useful for stressing boundary conditions.

* **Fine (`0 < grain < 1.0`)**

  * stride = `int(tile_side * grain)`
  * offset = 0 (aligned, denser grid)
  * Provides sharper boundary fidelity, at the cost of overlapping placements.

Renderer behavior is “last write wins” when placements overlap, which crisps up edges in typical mosaic use cases.

---

## Contributing

Contributions are welcome!

* Use [pre-commit](https://pre-commit.com) hooks (`ruff`, `black`, `mypy`, `pytest`).
* Run the test suite with `pytest`.
* Open issues or PRs with a clear description.
* For larger features, open an issue first to discuss direction.

---

## License

Licensed under the **MIT License**. See [LICENSE](LICENSE) for details.

# mosaic-builder

A Python library for reading photos and building **photo mosaics**.
The library is designed to support creative/art projects where you want to take a collection of “source” photos (tiles) and reassemble them into a mosaic version of a “target” image.

---

## Purpose

* Provide a **reusable library** for tiling, indexing, and querying photos.
* Make it easy to ingest large sets of source images into a database (SQLite/DuckDB).
* Allow flexible nearest-neighbor search backends (KD-Tree, HNSW, Faiss).
* Serve as the backbone for art projects (e.g. “Views from the Urinal”) that require organizing, analyzing, and recombining photos into mosaics.
* Be **data-backend-agnostic**, with interfaces abstracting storage and search.

---

## What is *not* the purpose

* This is **not** a full GUI mosaic editor.
* This is **not** a drop-in replacement for photo cataloging tools (e.g., Lightroom).
* This is **not** optimized yet for distributed, billion-tile datasets (though the API leaves room for scaling).
* It is **not** a general-purpose image processing library — it focuses narrowly on mosaic workflows.

---

## How to Use

### Install

```bash
# clone repo and install dev version
git clone https://github.com/jedmitten/mosaic_builder.git
cd mosaic_builder
uv sync  # or: pip install -e .
```

Optional extras:

```bash
uv sync --extra analytics  # enable DuckDB + Pandas
uv sync --extra debug      # enable matplotlib debug visuals
```

### CLI

```bash
# ingest source photos into a DuckDB-backed store
mosaic-builder ingest --images-dir gallery --store duckdb:///mosaic.duckdb

# build a KDTree index of tiles
mosaic-builder build-index --store duckdb:///mosaic.duckdb --index tiles_kdtree.pkl

# generate a mosaic from a target image
mosaic-builder build-mosaic --target urinal.jpg --index tiles_kdtree.pkl --out mosaic.png
```

### Python API

```python
from mosaic_builder.pipeline import ingest_dir
from mosaic_builder.stores.factory import open_store

store = open_store("duckdb:///mosaic.duckdb")
ingest_dir("duckdb:///mosaic.duckdb", "gallery", tile_w=24, tile_h=24)
```

---

## How to Contribute

Contributions are welcome!

* Use [pre-commit](https://pre-commit.com) hooks (`ruff`, `black`, `mypy`, `pytest`) to keep code style consistent.
* Run the test suite with `pytest`.
* Open an issue or pull request with a clear description of the change.
* For larger features, please discuss in an issue before coding to ensure alignment.

---

## License

This project is licensed under the terms of the **MIT License**.
See the [LICENSE](LICENSE) file for full text.

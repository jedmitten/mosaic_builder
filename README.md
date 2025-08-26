# mosaic-builder

A Python library for reading photos and building **photo mosaics**.

* Ingests a folder of photos, slices them into **tiles**, and stores their average Lab color.
* Supports multiple **tile sizes per photo** via a normalized `grids` table.
* Offers pluggable nearest-neighbor backends (KD-Tree now; ANN later).
* Storage backends: **SQLite** or **DuckDB** (choose at runtime).

---

## Purpose

* Provide a reusable, scriptable toolkit for **mosaic-style art projects**.
* Make ingestion/indexing/querying reliable and resumable.
* Keep storage and search **backend-agnostic** with clean interfaces.

---

## Not the Purpose

* Not a GUI editor or general photo manager.
* Not optimized (yet) for multi-billion-tile, distributed compute.
* Not a general image processing framework.

---

## Install

```bash
git clone https://github.com/jedmitten/mosaic_builder.git
cd mosaic_builder

# core dependencies (numpy, pillow, scipy, typer, etc.)
uv sync

# optional extras
uv sync --extra analytics   # duckdb + pandas
uv sync --extra debug       # matplotlib debug visuals
```

---

## CLI Usage

### Ingest photos → tiles (per grid size)

```bash
# Ingest all images in ./gallery at 24×24 tiles
mosaic-builder ingest --images-dir ./gallery \
  --store duckdb:///mosaic.duckdb \
  --tile-px 24 \
  --debug-dir ./debug
```

Re-ingest at a different size (coexists as a separate grid):

```bash
mosaic-builder ingest --images-dir ./gallery \
  --store duckdb:///mosaic.duckdb \
  --tile-px 102 \
  --debug-dir ./debug
```

* Each `(photo, tile size)` combination is a **grid**.
* Existing grids are skipped automatically.
* Force refresh for a grid size with `--reingest`.

---

### Build an index of tiles (KD-Tree)

```bash
mosaic-builder index \
  --store duckdb:///mosaic.duckdb \
  --index-path tiles_kdtree.pkl \
  --debug-dir ./debug
```

---

### Build a mosaic from a target image

```bash
mosaic-builder mosaic \
  --target ./target.jpg \
  --store duckdb:///mosaic.duckdb \
  --index-path tiles_kdtree.pkl \
  --out mosaic.png \
  --debug-dir ./debug
```

---

### Reset the database

```bash
# Delete rows (keep schema + indexes)
mosaic-builder reset-db --store duckdb:///mosaic.duckdb --mode wipe -y

# Drop tables/sequences and recreate schema + indexes
mosaic-builder reset-db --store duckdb:///mosaic.duckdb --mode drop -y

# Delete the DB file itself (dangerous)
mosaic-builder reset-db --store duckdb:///mosaic.duckdb --nuke -y
```

---

## Python API Example

```python
from pathlib import Path
from mosaic_builder.pipeline import ingest_dir
from mosaic_builder.stores.factory import open_store

store_url = "duckdb:///mosaic.duckdb"

# Ingest a folder at 24px tiles
ingest_dir(store_url, Path("gallery"), tile_w=24, tile_h=24, debug_dir=Path("debug"))

# Access vectors for indexing
store = open_store(store_url)
ids, vecs = store.all_tile_vectors()  # ids: List[int], vecs: np.ndarray (N,3) in Lab
store.close()
```

---

## Project Schema

* **photos**: `id`, `path (UNIQUE)`, `width`, `height`
* **grids**: `id`, `photo_id`, `tile_w`, `tile_h`, `cols`, `rows`, `UNIQUE(photo_id, tile_w, tile_h)`
* **tiles**: `id`, `grid_id`, `x`, `y`, `l`, `a`, `b`, `UNIQUE(grid_id, x, y)`

This design allows the same photo to have multiple tilings (24×24, 102×102, etc.) without conflicts.

---

## Contributing

* Run formatting/linting/type checks via pre-commit:

  ```bash
  pre-commit install
  pre-commit run --all-files
  ```
* Run tests:

  ```bash
  uv run pytest -q
  ```
* Open issues/PRs with a concise description and reproduction steps.
* For larger features, please start with an issue to align on approach.

---

## License

Licensed under the **MIT License**. See [LICENSE](LICENSE).

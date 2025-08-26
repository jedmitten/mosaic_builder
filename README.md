# mosaic-builder

A Python library for reading photos and building **photo mosaics**.

- Ingests a folder of photos, slices them into **tiles**, stores average Lab color.
- Supports multiple **tile sizes per photo** via a normalized `grids` table.
- Offers pluggable nearest-neighbor backends (KD-Tree now; ANN later).
- Storage backends: **SQLite** or **DuckDB** (choose at runtime).

---

## Purpose

- Provide a reusable, scriptable toolkit for **mosaic-style** art projects.
- Make ingestion/indexing/querying reliable and resumable.
- Keep storage and search **backend-agnostic** with clean interfaces.

## Not the Purpose

- Not a GUI editor or general photo manager.
- Not optimized (yet) for multi-billion-tile, distributed compute.
- Not a general image processing framework.

---

## Install

```bash
git clone https://github.com/jedmitten/mosaic_builder.git
cd mosaic_builder

# core (numpy, pillow, scipy, typer)
uv sync

# optional extras
uv sync --extra analytics   # duckdb + pandas
uv sync --extra debug       # matplotlib debug visuals
````

---

## CLI Usage

### Ingest photos → tiles (per grid size)

```bash
# Create (or re-use) a DB and ingest all images in ./gallery at 24×24 tiles
mosaic-builder ingest --images-dir ./gallery --store duckdb:///mosaic.duckdb --tile-px 24 --debug-dir ./debug

# Re-ingest the same photo set at 32×32 tiles; coexists with 24×24
mosaic-builder ingest --images-dir ./gallery --store duckdb:///mosaic.duckdb --tile-px 32 --debug-dir ./debug
```

Resuming behaviors:

* If a **grid** (photo + tile size) already has tiles, ingest **skips** it.
* Force refresh for a grid size with:

  ```bash
  mosaic-builder ingest --images-dir ./gallery --store duckdb:///mosaic.duckdb --tile-px 32 --reingest
  ```

### Build an index of tiles (KD-Tree)

```bash
mosaic-builder build-index --store duckdb:///mosaic.duckdb --index tiles_kdtree.pkl --debug-dir ./debug
```

*(Future)*: `--tile-size <N>` to index only tiles from a given grid size.

### Build a mosaic from a target image

```bash
mosaic-builder build-mosaic --target ./target.jpg \
  --store duckdb:///mosaic.duckdb \
  --index tiles_kdtree.pkl \
  --out mosaic.png \
  --debug-dir ./debug
```

### Reset the database (useful during development)

```bash
# Delete rows (keep schema and indexes)
mosaic-builder reset-db --store duckdb:///mosaic.duckdb --mode wipe -y

# Drop tables/sequences and recreate schema + indexes
mosaic-builder reset-db --store duckdb:///mosaic.duckdb --mode drop -y

# Nuke the DB file itself (dangerous)
mosaic-builder reset-db --store duckdb:///mosaic.duckdb --nuke -y
```

---

## Python API (snippet)

```python
from pathlib import Path
from mosaic_builder.pipeline import ingest_dir
from mosaic_builder.stores.factory import open_store

store_url = "duckdb:///mosaic.duckdb"

# Ingest a folder at 24px tiles; creates per-photo grids and tiles
ingest_dir(store_url, Path("gallery"), tile_w=24, tile_h=24, debug_dir=Path("debug"))

# Access vectors for indexing
store = open_store(store_url)
ids, vecs = store.all_tile_vectors()  # ids: List[int], vecs: np.ndarray (N,3) in Lab
store.close()
```

---

## Project Structure (storage model)

* **photos**: `id`, `path (UNIQUE)`, `width`, `height`
* **grids**: `id`, `photo_id`, `tile_w`, `tile_h`, `cols`, `rows`, `UNIQUE(photo_id, tile_w, tile_h)`
* **tiles**: `id`, `grid_id`, `x`, `y`, `l`, `a`, `b`, `UNIQUE(grid_id, x, y)`

This lets the same photo have multiple tilings (24×24, 32×32, …) without conflicts.

---

## Contributing

* Run formatting/linting/type checks via pre-commit:

  ```bash
  pre-commit install
  pre-commit run --all-files
  ```
* Tests:

  ```bash
  uv run pytest -q
  ```
* Open issues/PRs with a concise description and reproduction steps. For larger features, please start with an issue to align on approach.

---

## License

Licensed under the **MIT License**. See [LICENSE](LICENSE).

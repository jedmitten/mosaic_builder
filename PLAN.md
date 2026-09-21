# Mosaic Builder — Execution Plan

This document is written for an implementing agent. Follow the tasks **in order**.
Each task is self-contained: it says what to change, what "done" means, and how to verify.
Do not skip ahead. Do not invent extra features. If a task's verification fails, fix it before moving on.

---

## 0. Ground rules (read before every task)

1. **Run tests with pytest, never unittest.** Command: `uv run pytest tests/ -q`. All tests must pass before a task is considered done.
2. **Work test-first.** For every new function: write the failing test, run it to see it fail, then implement until it passes.
3. **One task per commit.** Commit message format: short imperative sentence, e.g. `add matcher grid analysis`. Never add AI attribution to commits or code.
4. **Never commit these files:** `mosaic.duckdb`, `preview.html`, `mosaic.png`, `match.json`, anything in `gallery/`. Task 0 adds them to `.gitignore`.
5. **Do not touch `gallery/`.** It is a symlink to a personal photo folder outside the repo. Tests must generate their own images with `PIL.Image.new(...)` in a `tempfile.TemporaryDirectory()`.
6. **Do not add dependencies** beyond `numpy`, `pillow`, `duckdb` without a stated reason in the commit message.
7. **Keep CLIs argparse-based** and runnable via `uv run python -m mosaic_builder.<module>`.
8. **Never write migrations.** If the DuckDB schema changes, the rule is: delete the `.duckdb` file and re-ingest.

---

## 1. Facts about the codebase you must know

These are non-obvious and will cause bugs if you guess.

| Fact | Detail |
|---|---|
| LAB column naming | In the `tiles` table, `mean_b` is **RGB blue**. `mean_bb` is **LAB b\***. `mean_L` and `mean_a` are LAB. Never confuse `mean_b` and `mean_bb`. |
| Tile identity | `tiles` primary key is `(image_id, tile_side, tile_index)`. A tile is not uniquely identified by `(image_id, tile_index)` alone. |
| One DB = one tile side | Multiple `tile_side` values in one DB are **not supported** (re-ingesting deletes all tiles for an image regardless of side). Every matcher/renderer read must still filter `WHERE tile_side = ?` so behaviour is well-defined. |
| LAB conversion | `tiler._srgb_to_lab(arr)` converts an `(H, W, 3)` uint8 sRGB array to float32 LAB. `tiler.mean_lab(img)` returns `(L, a, b)`. `tiler.delta_e(lab1, lab2)` is CIE76 Euclidean distance. Reuse these; do not reimplement. |
| Target images may be RGBA | `examples/target_images/target_8bit_checkered_floor_01.png` is 1024×1024 **RGBA**. Always `.convert("RGB")` after loading (`tiler.load_image` already does this). |
| Progress bar helper | `progress.iter_with_progress(items, desc, enabled)` is a generator that prints a text progress bar. Reuse it; do not write another. `ingest._iter_with_progress` is a backwards-compatible alias. |
| Schema version | After Task 1, the database carries a `schema_meta` row holding `SCHEMA_VERSION`. `ensure_schema` raises `SchemaVersionError` for a legacy, older, or newer database. There are no migrations: the fix is always to delete the `.duckdb` file and re-ingest. |
| Transactions | `ingest_gallery` wraps each image in `BEGIN`/`COMMIT`/`ROLLBACK`. Keep that pattern for any new write path. |
| Public API | `mosaic_builder/__init__.py` re-exports the store functions. When you add a store function, add it to both the import list and `__all__`. |
| Toolchain | Python 3.10, duckdb 1.4.2, pillow 12, numpy 2.2. Use `uv run ...` for everything. |

---

## 2. Review findings (what is wrong today)

Verified by running code, not by reading it.

| # | Finding | Severity | Fixed in |
|---|---|---|---|
| F1 | Phase 1 (LAB descriptors, decoupled ingest/preview, sequence IDs) is implemented and all 19 tests pass, but **none of it is committed**. The working tree differs from HEAD in every source file. | High | Task 0 |
| F2 | `mosaic.duckdb` in the repo root was ingested with the **old schema** (no LAB columns). `ensure_schema` succeeds, then `get_tile_lab_descriptors` raises `Binder Error: Referenced column "mean_L" not found`. No version check exists. | High | Task 1 |
| F3 | `get_all_tiles(conn, random_n=N)` raises `Parser Error: Only constants are supported in sample clause`. DuckDB does not accept a bound parameter inside `USING SAMPLE (? ROWS)`. No test covers it. | Medium | Task 1 |
| F4 | `get_tile_png(conn, image_id, tile_index)` does not filter on `tile_side`, so the lookup is ambiguous against the primary key. | Medium | Task 1 |
| F5 | `.gitignore` does not exclude `mosaic.duckdb` (11 MB) or `preview.html` (75 MB). Both are untracked and one `git add .` away from being committed. | High | Task 0 |
| F6 | The `gallery` **symlink** (to `~/Downloads/...`) is tracked in git. `.gitignore` has `**/gallery/` but that only ignores a directory, not the symlink file. | Medium | Task 0 |
| F7 | README is stale: the test command uses `unittest discover`, which silently skips the pytest-style functions in `tests/test_tiler.py`. The preview quickstart passes a positional `gallery` argument and `--tile-side`, neither of which `preview.py` accepts. | Medium | Task 0 |
| F8 | `pre-commit` is a dev dependency but there is no `.pre-commit-config.yaml`. No lint or format config exists. No `[tool.pytest.ini_options]` in `pyproject.toml`. | Low | Task 0 |
| F9 | `notebooks/visual_demo.ipynb` is 1.3 MB of saved outputs and hard-codes three personal gallery filenames, so it cannot run for anyone else. | Low | Task 7 |
| F10 | `CONTEXT.md` says `duckdb_store.py` has "CASCADE deletes". It does not; deletion is manual in `upsert_image`. Minor doc inaccuracy. | Low | Task 7 |

Nothing in `tiler.py` or the ingest path needs changing for the pipeline to work. The LAB math was spot-checked (white ≈ L100, black ≈ L0, red has strongly positive a\*).

---

## 3. Target architecture

```
Gallery dir ──ingest.py──▶ DuckDB (images, tiles) ──preview.py──▶ preview.html
                                   │
Target image ──matcher.py──────────┤  analyze_target ──▶ TargetGrid
                                   │  match_grid      ──▶ MatchResult ──▶ match.json
                                   │
match.json ────renderer.py─────────┘  assemble_mosaic ──▶ mosaic.png
                                                       (optional blend with target)

__main__.py: one dispatcher exposing ingest | preview | match | render | mosaic | validate
```

New files: `src/mosaic_builder/matcher.py`, `src/mosaic_builder/renderer.py`, `src/mosaic_builder/__main__.py`, `src/mosaic_builder/validate.py`, and one test file per new module.

---

## 4. Tasks

### Task 0 — Commit Phase 1 and fix repo hygiene

**Goal:** Get the working tree into a clean, committed state so every later task starts from a known baseline.

**Files:** `.gitignore`, `README.md`, `pyproject.toml`, `.pre-commit-config.yaml` (new), git index.

**Steps:**

1. Append to `.gitignore`:
   ```
   # generated artifacts
   *.duckdb
   *.duckdb.wal
   preview.html
   mosaic.png
   match.json
   .uv-cache/
   gallery
   ```
2. Remove the tracked symlink from the index without deleting it from disk: `git rm --cached gallery`.
3. Delete the stale database: `rm mosaic.duckdb`. (It is on the old schema and cannot be read. It is regenerated by ingest.)
4. Delete `preview.html` (75 MB, regenerated by preview).
5. In `pyproject.toml` add:
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   ```
6. Create `.pre-commit-config.yaml` with two hooks only: `ruff` (lint + format) and `nbstripout`. Add `ruff` and `nbstripout` to the `dev` dependency group. Run `uv sync`. Do not add any other hooks.
7. Fix `README.md`:
   - Replace the unittest command with `uv run pytest tests/ -q`.
   - Replace the Quickstart with two commands that actually match the current CLIs:
     - `uv run python -m mosaic_builder.ingest gallery --db mosaic.duckdb --tile-side 64`
     - `uv run python -m mosaic_builder.preview --db mosaic.duckdb --out preview.html --first-n 25`
8. Commit everything **except** `notebooks/` in one commit: `commit phase 1: LAB descriptors, decoupled ingest/preview, repo hygiene`. Commit `notebooks/` separately after Task 7 strips its outputs (or leave it untracked until then).

**Done when:**
- `git status` shows a clean tree apart from `notebooks/`.
- `git ls-files | grep -c gallery` prints `0`.
- `uv run pytest tests/ -q` reports 19 passed.
- `uv run pre-commit run --all-files` passes.

---

### Task 1 — Schema versioning, store bug fixes

**Goal:** Make `duckdb_store.py` safe to build on: a database carries an explicit schema version,
opening a stale or future database fails with a clear actionable error instead of a DuckDB internal
error, and the known read bugs are fixed.

**Files:** `src/mosaic_builder/duckdb_store.py`, `src/mosaic_builder/__init__.py`, `tests/test_duckdb_store.py`, `tests/test_schema_version.py` (new).

#### 1a. Schema version (do this first)

Add to `duckdb_store.py`:

- `SCHEMA_VERSION: int = 2` — module constant. Bump it whenever `SCHEMA_STATEMENTS` changes shape.
- `class SchemaVersionError(RuntimeError)` — raised for every schema mismatch. Export from `__init__.py`.
- `EXPECTED_TILE_COLUMNS: frozenset[str]` — the 13 column names in `_TILE_COLS`.
- A third entry in `SCHEMA_STATEMENTS`:
  ```sql
  CREATE TABLE IF NOT EXISTS schema_meta (
      key VARCHAR PRIMARY KEY,
      value VARCHAR NOT NULL,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  ```
- `get_schema_version(conn) -> int | None` — returns the integer stored under key `schema_version`,
  or `None` if the `schema_meta` table does not exist or holds no such row. Must not raise on a
  database that has no `schema_meta` table.
- `stamp_schema_version(conn, version: int = SCHEMA_VERSION) -> None` — upsert the row.

Rewrite `ensure_schema(conn, statements=None)` to run in this exact order:

1. **Before creating anything**, record whether a legacy database is present: `tiles` or `images`
   exists in `information_schema.tables` **and** `schema_meta` does not.
2. Execute the `CREATE TABLE IF NOT EXISTS` statements.
3. If step 1 found a legacy database, raise `SchemaVersionError` whose message contains the words
   `out of date` and `delete` and names the database's missing columns when any are missing.
4. Read the version. If it is `None` (a genuinely fresh database), call `stamp_schema_version` and
   skip to step 7.
5. If the version is **less than** `SCHEMA_VERSION`, raise `SchemaVersionError` naming both versions
   and instructing the user to delete the `.duckdb` file and re-ingest. There are no migrations.
6. If the version is **greater than** `SCHEMA_VERSION`, raise `SchemaVersionError` saying the file
   was written by a newer mosaic-builder and to upgrade the package.
7. Column guard: `DESCRIBE tiles`, compare against `EXPECTED_TILE_COLUMNS`, and raise
   `SchemaVersionError` listing every missing column.

`ensure_schema` must be idempotent: calling it twice on a fresh database must not raise and must
leave exactly one `schema_meta` row.

**Tests — put these in `tests/test_schema_version.py`:**

1. Fresh database: after `ensure_schema`, `get_schema_version(conn) == SCHEMA_VERSION`.
2. Idempotent: call `ensure_schema` twice, no raise, and `SELECT count(*) FROM schema_meta` is 1.
3. `get_schema_version` on a database with no `schema_meta` table returns `None` and does not raise.
4. **Legacy database** (this is the bug that shipped): create `images` and `tiles` by hand with the
   pre-LAB columns only (`image_id, tile_index, crop_box, coverage, score, mean_r, mean_g, mean_b,
   descriptor, tile_png`), insert one row of each, then call `ensure_schema`. Assert
   `SchemaVersionError` is raised and the message mentions `delete`. Assert it is **not** a
   `duckdb.BinderException`.
5. **Downgrade**: fresh database, then overwrite the stored version with `SCHEMA_VERSION - 1`, call
   `ensure_schema`, assert `SchemaVersionError` naming both version numbers.
6. **Future version**: store `SCHEMA_VERSION + 1`, assert `SchemaVersionError` whose message
   mentions upgrading.
7. **Missing column guard**: stamp the correct version but create a `tiles` table missing `mean_L`;
   assert `SchemaVersionError` whose message contains `mean_L`.
8. `ingest_gallery` against a legacy database surfaces `SchemaVersionError` rather than a DuckDB
   error (build the legacy database, then call `ingest_gallery` on a two-image temp gallery).

#### 1b. Store bug fixes

1. **Fix `random_n`.** `get_all_tiles(conn, random_n=N)` currently raises
   `Parser Error: Only constants are supported in sample clause`. Replace the `USING SAMPLE (? ROWS)`
   query with `ORDER BY random() LIMIT {int(random_n)}`.
   - Test: insert 5 tiles, request `random_n=3`, assert exactly 3 rows and all
     `(image_id, tile_index)` pairs distinct. Assert `random_n=99` on 5 tiles returns 5.
2. **Add `tile_side` to `get_tile_png`.** New signature
   `get_tile_png(conn, image_id, tile_index, *, tile_side=None)`; when not `None`, add
   `AND tile_side = ?`. Existing callers keep working.
   - Test: insert two tiles sharing `(image_id, tile_index)` but with different `tile_side` and
     different PNG bytes; assert each side returns its own bytes.
3. **Filter `get_tile_lab_descriptors` by tile side.** New signature
   `get_tile_lab_descriptors(conn, *, tile_side=None)`, same optional-filter pattern.
4. **Add `get_tile_sides(conn) -> list[int]`** — `SELECT DISTINCT tile_side FROM tiles ORDER BY tile_side`.
   - Test: empty database returns `[]`; after inserting sides 32 and 64 returns `[32, 64]`.
5. **Add `get_tile_pngs_bulk(conn, keys, *, tile_side) -> dict[tuple[int, int], bytes]`** — `keys` is
   an iterable of `(image_id, tile_index)`. Fetch every matching row in **one** query. Missing keys
   are simply absent from the returned dict; do not raise. The renderer in Task 4 depends on this.
   - Test: insert 3 tiles, request 2 of them plus 1 nonexistent key, assert the dict holds exactly
     the 2 real keys with the right bytes.

Export `SCHEMA_VERSION`, `SchemaVersionError`, `get_schema_version`, `get_tile_sides`, and
`get_tile_pngs_bulk` from `__init__.py` (both the import list and `__all__`).

**Done when:** `uv run pytest tests/ -q` passes with at least 35 tests, `uv run ruff check src tests`
is clean, and this prints a friendly error rather than a traceback:
```bash
uv run python -c "
import duckdb, tempfile, pathlib
from mosaic_builder.duckdb_store import ensure_schema
p = pathlib.Path(tempfile.mkdtemp())/'legacy.duckdb'
c = duckdb.connect(str(p))
c.execute('CREATE TABLE images (image_id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL)')
c.execute('CREATE TABLE tiles (image_id INTEGER NOT NULL, tile_index INTEGER NOT NULL, crop_box TEXT NOT NULL, coverage REAL NOT NULL, score REAL NOT NULL, mean_r REAL NOT NULL, mean_g REAL NOT NULL, mean_b REAL NOT NULL, tile_png BLOB NOT NULL)')
try:
    ensure_schema(c)
except Exception as e:
    print(type(e).__name__, e)
"
```

---

### Task 2 — Matcher part 1: target analysis

**Goal:** Turn a target image into a grid of LAB descriptors.

**Files:** `src/mosaic_builder/matcher.py` (new), `tests/test_matcher.py` (new).

**Definitions (use these names exactly):**

- `grain` (int): the edge length in **target pixels** of one grid cell. A 1024-px-wide target with `grain=32` has 32 columns.
- `rows = height // grain`, `cols = width // grain`. Any remainder on the right/bottom edge is **dropped**. Document this in the docstring.
- The matcher never needs `tile_side`. `tile_side` only matters at render time.

**Dataclasses (all `@dataclass(frozen=True)`):**

- `CellDescriptor`: `row: int`, `col: int`, `lab: tuple[float, float, float]`
- `TargetGrid`: `rows: int`, `cols: int`, `grain: int`, `cells: list[CellDescriptor]` (row-major order, `len(cells) == rows * cols`)

**Function:**

- `analyze_target(image: PIL.Image.Image, *, grain: int) -> TargetGrid`
  - Convert image to RGB. Compute `rows`, `cols`. Raise `ValueError` if either is 0 (image smaller than one cell).
  - Convert the whole image once with `tiler._srgb_to_lab` (do **not** call `mean_lab` per cell; that is ~1000× slower). Slice the LAB array per cell and take the mean over the cell's pixels.
  - Return the grid.

**Tests:**

1. A 64×32 solid red image with `grain=16` → `rows=2`, `cols=4`, 8 cells, every cell's `lab` has `a > 20`.
2. A 70×40 image with `grain=32` → `rows=1`, `cols=2` (remainder dropped).
3. A 10×10 image with `grain=32` → `ValueError`.
4. Left half black, right half white, `grain` = half width → cell (0,0) has `L < 5`, cell (0,1) has `L > 95`.

**Done when:** the four tests pass.

---

### Task 3 — Matcher part 2: greedy grid matching, JSON output, CLI

**Goal:** Assign the best tile to each cell under reuse constraints, and persist the result as JSON.

**Files:** `src/mosaic_builder/matcher.py`, `tests/test_matcher.py`.

**Dataclasses:**

- `CellMatch`: `row: int`, `col: int`, `image_id: int`, `tile_index: int`, `delta_e: float`
- `MatchResult`: `rows: int`, `cols: int`, `grain: int`, `tile_side: int`, `db_path: str`, `matches: list[CellMatch]` (row-major)

**Function:**

- `match_grid(grid: TargetGrid, descriptors: list[dict], *, tile_side: int, db_path: str, max_reuse: int = 0, min_repeat_dist: int = 0) -> MatchResult`
  - `descriptors` is the list returned by `get_tile_lab_descriptors`. Read LAB from keys `mean_L`, `mean_a`, **`mean_bb`**.
  - Raise `ValueError("No tiles in database")` if `descriptors` is empty.
  - Build a numpy array `T` of shape `(n_tiles, 3)` and `C` of shape `(n_cells, 3)`. Compute the full distance matrix `D = sqrt(((C[:, None, :] - T[None, :, :]) ** 2).sum(-1))`, shape `(n_cells, n_tiles)`. For 4096 cells × 2000 tiles this is ~65 MB of float64; acceptable. If `n_cells * n_tiles > 20_000_000`, process cells in chunks of 1024 rows instead.
  - Walk cells in row-major order. For each cell, iterate candidate tiles in ascending distance (`np.argsort(D[i])`) and take the **first** candidate that satisfies both constraints:
    - `max_reuse`: if `> 0`, the tile has been used fewer than `max_reuse` times so far.
    - `min_repeat_dist`: if `> 0`, the tile has not been placed at any cell `(r, c)` with `max(|r - row|, |c - col|) < min_repeat_dist` (Chebyshev distance).
  - If **no** candidate satisfies the constraints, fall back to the unconstrained best tile and continue. Never raise here.
  - Track usage with a `dict[(image_id, tile_index), int]` and placements with a `dict[(image_id, tile_index), list[(row, col)]]`.

**JSON I/O:**

- `save_match_result(result: MatchResult, path: Path) -> None` and `load_match_result(path: Path) -> MatchResult`.
- JSON shape (keys exact):
  ```json
  {
    "rows": 2, "cols": 3, "grain": 32, "tile_side": 64, "db_path": "mosaic.duckdb",
    "matches": [
      {"row": 0, "col": 0, "image_id": 7, "tile_index": 1, "delta_e": 3.21}
    ]
  }
  ```

**Top-level convenience:**

- `run_match(target_path: Path, db_path: Path, *, grain: int, tile_side: int | None, max_reuse: int, min_repeat_dist: int, show_progress: bool) -> MatchResult`
  - Loads the image via `tiler.load_image`, opens the DB, calls `ensure_schema`.
  - If `tile_side` is `None`: call `get_tile_sides`. If exactly one side exists, use it. If zero, raise `ValueError("No tiles in database")`. If more than one, raise `ValueError` listing them and asking for `--tile-side`.
  - Calls `analyze_target`, `get_tile_lab_descriptors(conn, tile_side=...)`, `match_grid`.

**CLI** (`main()` + `if __name__ == "__main__"`):

```
python -m mosaic_builder.matcher TARGET --db mosaic.duckdb --grain 32 [--tile-side 64] [--max-reuse 0] [--min-repeat-dist 0] --out match.json [--no-progress]
```
Prints one summary line: rows, cols, mean delta_e, number of distinct tiles used.

**Tests:**

1. Descriptors for a red, green, blue tile; a 2×2 grid of red/green/blue/red cells → the matches pick the expected tile for each cell and every `delta_e` is < 1.0.
2. `max_reuse=1` with three red cells and tiles [red, dark-red, orange] → each tile is used at most once, and the first cell gets red.
3. `min_repeat_dist=2` on a 1×4 row of identical cells with two near-identical tiles → the same tile is never used in adjacent columns.
4. Constraints impossible to satisfy (1 tile, `max_reuse=1`, 4 cells) → does not raise, all 4 cells use the one tile.
5. Empty descriptor list → `ValueError`.
6. `save_match_result` then `load_match_result` round-trips to an equal `MatchResult`.
7. `run_match` end-to-end: ingest two solid-colour images into a temp DB, run against a solid-colour target, assert the result has the right dimensions and each match references a tile that exists.

**Done when:** all tests pass and this command produces a JSON file:
```bash
uv run python -m mosaic_builder.ingest gallery --db mosaic.duckdb --tile-side 64
uv run python -m mosaic_builder.matcher examples/target_images/target_8bit_checkered_floor_01.png --db mosaic.duckdb --grain 32 --out match.json
```

---

### Task 4 — Renderer: assemble mosaic, optional blend, CLI

**Goal:** Turn `match.json` plus the database into `mosaic.png`.

**Files:** `src/mosaic_builder/renderer.py` (new), `tests/test_renderer.py` (new).

**Functions:**

- `assemble_mosaic(result: MatchResult, conn) -> PIL.Image.Image`
  - Canvas size is `(cols * tile_side, rows * tile_side)`, mode RGB.
  - Collect the set of distinct `(image_id, tile_index)` keys from `result.matches`. Fetch them with **one** call to `get_tile_pngs_bulk(conn, keys, tile_side=result.tile_side)`. Decode each PNG once into a `dict[key, PIL.Image]`.
  - If any key is missing from the bulk result, raise `KeyError` naming it.
  - Paste each tile at `(col * tile_side, row * tile_side)`.
- `blend_with_target(mosaic: Image, target: Image, alpha: float) -> Image`
  - Resize `target` (RGB) to `mosaic.size` with LANCZOS, then `Image.blend(mosaic, target, alpha)`. `alpha=0.0` returns the mosaic unchanged; `alpha=1.0` returns the resized target.
  - Raise `ValueError` if alpha is outside `[0, 1]`.
- `run_render(match_path: Path, db_path: Path, out_path: Path, *, blend: float = 0.0, target_path: Path | None = None) -> Path`
  - Loads the result, opens the DB, assembles, blends if `blend > 0` (requires `target_path`; raise `ValueError` if missing), saves PNG, returns `out_path`.

**CLI:**
```
python -m mosaic_builder.renderer match.json --db mosaic.duckdb --out mosaic.png [--blend 0.0 --target TARGET]
```

**Tests:**

1. Build a temp DB with two 8×8 tiles (solid red, solid blue). Construct a 2×2 `MatchResult` by hand (red, blue / blue, red). Output size is 16×16. Pixel `(0,0)` is red, `(15,0)` is blue, `(0,15)` is blue, `(15,15)` is red.
2. A `MatchResult` referencing a tile that does not exist → `KeyError`.
3. `blend_with_target` with `alpha=0` equals the input mosaic pixel-for-pixel; with `alpha=1` equals the resized target.
4. `blend_with_target` with `alpha=1.5` → `ValueError`.

**Done when:** tests pass and this produces a viewable image:
```bash
uv run python -m mosaic_builder.renderer match.json --db mosaic.duckdb --out mosaic.png
open mosaic.png
```

---

### Task 5 — Unified CLI

**Goal:** One entry point, `python -m mosaic_builder <subcommand>`, with a `mosaic` subcommand that runs match + render in one step.

**Files:** `src/mosaic_builder/__main__.py` (new), `tests/test_cli.py` (new).

**Steps:**

1. Create an argparse parser with subparsers: `ingest`, `preview`, `match`, `render`, `mosaic`, `validate`. Each of these except `mosaic` delegates to the existing module's argument set (move each module's parser construction into a function `build_parser(sub=None)` so it can be attached as a subparser; keep `python -m mosaic_builder.ingest` working).
2. `mosaic` subcommand takes `TARGET --db --grain [--tile-side] [--max-reuse] [--min-repeat-dist] [--blend] --out mosaic.png [--keep-match match.json]`. It calls `run_match` then `run_render` in memory (no JSON round-trip unless `--keep-match` is given).
3. Add `[project.scripts] mosaic-builder = "mosaic_builder.__main__:main"` to `pyproject.toml` so `uv run mosaic-builder ...` also works.

**Tests:**

1. `python -m mosaic_builder --help` exits 0 and lists all six subcommands (use `subprocess.run` with `sys.executable`).
2. End-to-end in a temp dir: write 3 solid-colour gallery images, run `ingest`, then `mosaic` against a 64×64 solid-colour target with `--grain 16`. Assert the output PNG exists and is 4×tile_side square.

**Done when:** tests pass and this one command produces a mosaic from scratch:
```bash
uv run python -m mosaic_builder mosaic examples/target_images/target_8bit_checkered_floor_01.png --db mosaic.duckdb --grain 32 --out mosaic.png
```

---

### Task 6 — Validate subcommand (gallery quality report)

**Goal:** A read-only report that tells the user whether the gallery is good enough before they spend time rendering.

**Files:** `src/mosaic_builder/validate.py` (new), `tests/test_validate.py` (new).

`validate.py` ships its own `build_parser()` and `main()` so it runs as `python -m mosaic_builder.validate`. Task 5 wires it in as a subcommand; **do not edit `__main__.py` in this task.**

**Function:** `gallery_report(conn, *, tile_side: int | None = None) -> dict` returning:

| Key | Meaning |
|---|---|
| `image_count`, `tile_count`, `tile_sides` | Basic counts |
| `lab_ranges` | `{"L": [min, max], "a": [min, max], "b": [min, max]}` |
| `mean_nearest_neighbor_delta_e` | For each tile, distance to its nearest other tile; report the mean. Low values (< 3) mean many near-duplicate tiles. |
| `coverage_histogram` | Counts of tiles in coverage buckets `[0-0.25, 0.25-0.5, 0.5-0.75, 0.75-1.0]` |
| `low_texture_tiles` | List of `(image_id, tile_index, score)` for the 10 lowest `score` values |

**CLI:** `python -m mosaic_builder validate --db mosaic.duckdb [--tile-side 64] [--json]`. Default output is a human-readable table; `--json` dumps the dict.

**Tests:**
1. Empty DB → `image_count == 0`, `tile_count == 0`, no exception.
2. Two tiles with LAB (50,0,0) and (50,3,4) → `mean_nearest_neighbor_delta_e == 5.0` (within 1e-6).

**Done when:** tests pass and `uv run python -m mosaic_builder validate --db mosaic.duckdb` prints a report.

---

### Task 7 — Docs, notebook, polish

**Goal:** Make the repo accurate and reproducible for the next person.

**Files:** `README.md`, `CONTEXT.md`, `notebooks/visual_demo.ipynb`, `ingest.py`, `matcher.py`, `renderer.py`.

**Steps:**

1. **Progress bars:** ~~Move the helper to `progress.py`.~~ **Already done** — `src/mosaic_builder/progress.py` exists, `ingest.py` imports it, and `tests/test_progress.py` covers it. Remaining work: wire `iter_with_progress` into the cell loop in `match_grid` (via `run_match`) and the paste loop in `assemble_mosaic`.
2. **Error messages:** every CLI must exit with code 1 and a one-line message (no traceback) for: missing target file, missing DB file, empty DB, out-of-date schema. Implement with a single `try/except (FileNotFoundError, ValueError, RuntimeError)` in each `main()`.
3. **Notebook:** replace the three hard-coded gallery filenames with "the first three files returned by `tiler.iter_gallery_images(GALLERY_DIR)`". Strip all outputs (`uv run nbstripout notebooks/visual_demo.ipynb`). Add a final section that runs `run_match` + `assemble_mosaic` on `examples/target_images/target_8bit_checkered_floor_01.png` and displays the result. Then commit `notebooks/`.
4. **CONTEXT.md:** remove the "CASCADE deletes" claim; add `matcher.py`, `renderer.py`, `validate.py`, `__main__.py` to the Modules list; replace "Next Build Steps" with the actual remaining ideas (see section 5 below).
5. **README.md:** Quickstart becomes the three-command flow: `ingest` → `validate` → `mosaic`. Document every CLI flag in a table. Explain `grain` vs `tile_side` in two sentences.

**Done when:** `uv run pre-commit run --all-files` passes, every command in the README runs as written, and `git status` is clean.

---

## 5. Decisions made in this plan (do not re-litigate)

| Decision | Rationale |
|---|---|
| Greedy raster-order matching with reuse/repeat constraints; no global optimiser | `CONTEXT.md` lesson 3. Revisit only after real mosaics show visible failures. |
| Mean LAB per cell and per tile (one descriptor each) | Simplest thing that produces a mosaic. A 2×2 sub-cell descriptor is the obvious next upgrade and is listed in section 6. |
| One `tile_side` per database file; reads still filter by it | The schema allows multiple sides but the write path does not. Filtering keeps behaviour defined without adding a feature nobody asked for. |
| No schema migrations; hard error + "delete and re-ingest" | Ingest of 480 images takes well under a minute. Migration code is not worth its maintenance. |
| `match.json` as the interface between matcher and renderer | Lets the user inspect and hand-edit assignments, and lets rendering be re-run with different `--blend` without re-matching. |
| Remainder pixels at the right/bottom of the target are dropped | Keeps the grid rectangular and every cell the same size. Padding would blur the edge cells' descriptors. |
| Bulk PNG fetch in the renderer from day one | Per-cell queries against a 4096-cell grid are noticeably slow in DuckDB; doing it right first costs nothing. |

---

## 6. After this plan (not scheduled)

Ideas worth doing next, in rough priority order. None of these should be started until Task 7 is committed.

1. **Sub-cell descriptors:** store a 2×2 (or 3×3) LAB grid per tile and per cell; match on the concatenated vector. This is the single biggest quality lever.

   **Measured evidence (480 photos, 1440 tiles, tile_side 64):** mean nearest-neighbour distance
   between tiles is 1.06, and 1.46 when siblings from the same photo are excluded. Only 125 of 1440
   tiles sit more than 3 units from their nearest neighbour in another photo. The gallery is
   therefore heavily clustered in colour space: hundreds of tiles are effectively interchangeable on
   mean colour alone. Two consequences follow. Reuse and repeat-distance constraints will be cheap
   to satisfy, because near-equivalent substitutes are plentiful. And mean colour alone is close to
   exhausted as a discriminator, so sub-cell descriptors are what will actually differentiate tiles.
   Re-measure with `python -m mosaic_builder.validate` after any change to tile extraction.
2. **Tile augmentation:** ingest horizontally flipped and 90°-rotated variants as extra tiles to enlarge a small gallery.
3. **Hue-shifted tinting at render time:** blend each tile toward the cell's mean colour by a small factor to hide colour-match error.
4. **Multi-side support done properly:** change `upsert_image` to preserve `image_id` and `upsert_tiles` to delete only `WHERE image_id = ? AND tile_side = ?`.
5. **Gallery symlink replacement:** a `--gallery` env var or config file so the notebook and README do not depend on a symlink.

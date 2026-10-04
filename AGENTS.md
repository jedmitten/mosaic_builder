# AGENTS.md

Instructions for AI agents working in this repository. Read this before making changes.

## 1. Project structure and intent

**mosaic-builder** turns a gallery of personal photos into a photo mosaic of a target image,
backed by DuckDB. See `README.md` for user-facing docs, `CONTEXT.md` for design intent and
validated assumptions, and `PLAN.md` for the execution history/backlog. Read `CONTEXT.md` before
any non-trivial change — it records *why* decisions were made, not just what the code does.

### Pipeline

```
Gallery dir → ingest.py → DuckDB (images + tiles) → preview.py  → preview.html
                                 │              └─→ validate.py → quality report
                                 │
Target image → matcher.py (analyze_target → match_grid) → MatchResult → match.json
                                 │
                       renderer.py (assemble_mosaic [+ blend]) → mosaic.png
```

### Modules (`src/mosaic_builder/`)

| Module | Responsibility |
|---|---|
| `tiler.py` | EXIF-aware image loading, character-tile extraction (texture-ranked square crops), resizing, mean RGB/LAB, CIE76 `delta_e`, fixture-detection scoring (`color_contrast_score`, `periodicity_score`, `fixture_likelihood_score`). |
| `duckdb_store.py` | Schema + `SCHEMA_VERSION`, read helpers, transactional upserts. `TILE_COLUMNS` is the single source of truth for the `tiles` table — the DDL, both SELECT lists, the row→dict mapping and the INSERT are all derived from it. No migrations — a version mismatch raises `SchemaVersionError` telling the user to delete and re-ingest. |
| `ingest.py` | Gallery → DuckDB, per-image transactions with rollback, returns `IngestSummary`. |
| `matcher.py` | `analyze_target` (grid of per-cell LAB descriptors) + `match_grid` (assignment minimising `delta_e + weight × reuse penalty`; the `--diversity` dial sets the weight, and the penalty is scaled by each tile's fair share so a dial position means the same thing on any gallery size). |
| `renderer.py` | Assembles the mosaic from a `MatchResult`, optional alpha blend toward target. |
| `validate.py` | Read-only gallery quality report (LAB ranges, nearest-neighbour diversity, coverage histogram, lowest-texture tiles, top fixture-candidate tiles). |
| `preview.py` | HTML preview of stored tiles. Reads only; never re-ingests. |
| `progress.py` | Shared text progress-bar helper. |
| `cli.py` | `cli_errors()` context manager — expected user errors (`FileNotFoundError`, `ValueError`, `RuntimeError`) become a one-line `error: ...` message + exit 1; everything else keeps its traceback. |
| `__main__.py` | Subcommand dispatcher. |

Every command module exposes the same shape: `build_parser(sub=None)`, `run_from_args(args)`,
`main(argv=None)`. Preserve this shape in any new module — it's what lets each run standalone and
attach to the dispatcher without duplicated argument definitions.

### Conventions

- Lint/format: `ruff` (line-length 110, `E/F/I/UP/B`, `E501` ignored). Run `uv run ruff check .` and
  `uv run ruff format .` before considering work done.
- Tests: `uv run pytest -q`, mirrored 1:1 under `tests/` (e.g. `tiler.py` → `test_tiler.py`).
- Notebook: `notebooks/visual_demo.ipynb` must run end-to-end on a fresh clone with no personal
  gallery (it falls back to synthetic images — see its Section 1). `nbstripout` is a pre-commit hook;
  never commit cell outputs by hand.
- Non-goals (do not casually reintroduce without discussion): alternative databases to DuckDB,
  schema migrations, a GUI editor, a plugin architecture.
- **Dependency policy: prefer existing, well-established packages over hand-rolled
  implementations of the same functionality.** Core runtime surface is `numpy`, `pillow`, `duckdb`,
  `scikit-image`. Adding a new dependency is fine — even preferred — when it replaces bespoke code
  for a solved problem (e.g. `scikit-image` was added for `threshold_otsu`/`filters.window` rather
  than hand-rolling Otsu thresholding and FFT windowing); still flag/discuss the addition rather
  than silently expanding the surface further. For a genuinely novel approach with no
  existing-package equivalent: build it, then see §5 for evaluating whether it should be
  contributed upstream rather than living as permanent bespoke code.

---

## 2. Tile Feature Agent

**Purpose:** add or explore alternative per-tile scoring/feature approaches — e.g. "texture"
(already implemented as `tiler.texture_score`), "whiteness", "non-whiteness", "colorfulness",
"entropy", "saturation" — when the user asks for a new way to characterize or select tiles.

**Pattern to follow** (`tiler.texture_score` is the reference implementation):

0. **Prefer an existing package over hand-rolled numpy.** Before writing a new feature as custom
   numpy code, check whether `numpy`/`scipy`/`scikit-image` already implements it, and use that
   instead of reinventing a solved problem. Worked example: `color_contrast_score` uses
   `skimage.filters.threshold_otsu` for its threshold search rather than a hand-rolled Otsu scan,
   and `periodicity_score` uses `skimage.filters.window` for FFT apodization rather than building a
   window from scratch. Only write genuinely custom numpy code for an approach with no
   existing-package equivalent — and when you do, see §5 (Package Fit & Upstreaming Agent) for what
   happens next.
1. Implement the feature as a pure function in `tiler.py`: takes a `PIL.Image` tile, returns a
   `float` (or a small tuple for multi-channel features), computed via `numpy` on the pixel array.
   No I/O, no DB access inside the function.
2. Decide which of three kinds of value the feature is, because each is stored differently:
   - **Transient** — computed at ingest only to rank/select tiles, like `texture_score`'s use inside
     `extract_character_tiles`. Wire it into the ranking; store nothing.
   - **Measured primitive** — a direct measurement of the pixels, like `mean_rgb`/`mean_lab`/
     `color_contrast`/`periodicity`. Persist it: add one `TileColumn(...)` entry to
     `duckdb_store.TILE_COLUMNS`, add the matching key in `ingest.py`'s tile dict, add a default in
     `tests/conftest.py`'s `_TILE_DEFAULTS`, and bump `SCHEMA_VERSION`. The DDL, SELECT lists,
     row→dict mapping and INSERT all derive from `TILE_COLUMNS`, so there is nothing else to edit.
     A schema bump is breaking for existing databases — the user must re-ingest; say so explicitly.
   - **Derived composite** — a function of other columns plus tunable constants, like
     `fixture_likelihood_score`. **Do not persist it.** Compute it on read (see
     `validate._fixture_candidate_tiles` and `preview._fixture_score`) so retuning a constant takes
     effect immediately instead of silently invalidating every stored row.
3. If the feature could plausibly become a matching axis (like LAB color), consider whether
   `matcher.analyze_target` / `match_grid` need a corresponding target-side descriptor and distance
   term. Don't wire it into matching unless asked — adding a feature function and adding a new
   matching dimension are different asks.
4. Add tests in `tests/test_tiler.py` (and `tests/test_duckdb_store.py` if persisted): at minimum a
   known-input/known-output case (e.g. a solid white tile should score ~0 "non-whiteness" and a
   solid black tile ~max). Tests build tile rows through `tests/conftest.py`'s `make_tile(**overrides)`
   — never hand-roll a tile dict in a test module, or the next schema change breaks it.
5. If the feature changes CLI-visible behavior (new flag, new `validate` report row), update
   `README.md`'s Commands tables and `CONTEXT.md`'s Validated Assumptions if it shifts a
   quality/variety tradeoff.

**Done-when:**
- New function(s) exist in `tiler.py` with names matching the feature (e.g. `whiteness_score`).
- `uv run pytest -q` passes, including new tests.
- `uv run ruff check .` is clean.
- If persisted: one `TILE_COLUMNS` entry added, `SCHEMA_VERSION` bumped, a fresh `ingest` run
  succeeds, `validate` still runs. If derived: nothing was added to the schema at all.
- README/CONTEXT updated if user-facing behavior changed; otherwise left alone.

---

## 3. Code Review Agent

**Purpose:** review changes to both the backend library (`src/mosaic_builder/`, `tests/`) and the
demonstration notebook (`notebooks/visual_demo.ipynb`) before they're considered done or committed.

**Backend review checklist:**
- `uv run ruff check .` and `uv run pytest -q` both pass.
- New/changed modules keep the `build_parser` / `run_from_args` / `main` shape (§1) if they're
  CLI-facing.
- User-causable errors are raised as `FileNotFoundError` / `ValueError` / `RuntimeError` so
  `cli.cli_errors()` reports them cleanly; don't let a bug masquerade as a user error, and don't let
  a real user error leak a raw traceback.
- Schema changes bump `SCHEMA_VERSION` in `duckdb_store.py` and are covered by
  `tests/test_schema_version.py`.
- LAB/color math changes are checked against `tests/test_tiler.py`'s known values — this is
  perceptual-distance code, silent regressions here are hard to notice visually.
- New dependencies beyond the core surface (§1) are fine when they replace bespoke code for a
  solved problem, per the dependency policy — but still flag/discuss the addition; this surface is
  deliberately kept small and deliberate, not organically grown.

**Notebook review checklist:**
- The notebook still runs top-to-bottom on a fresh clone with no `gallery/` symlink present
  (synthetic-image fallback in Section 1 must still trigger correctly).
- Imports at the top of the notebook match current function names/signatures in
  `src/mosaic_builder/` — a renamed function in the library is a common source of notebook rot.
  Diff the notebook's `from mosaic_builder...` imports against the actual module exports.
  Run `jupyter nbconvert --to script --stdout notebooks/visual_demo.ipynb` to inspect without
  executing.
  Note Section 10 is committed-output-only (full gallery required) — don't expect it to execute.
- No raw cell outputs committed (`nbstripout` should have stripped them — check `git diff` on the
  notebook for output/metadata noise).
- Any README code snippet that's supposed to match notebook/CLI behavior still matches after a
  flag/default changes (`README.md`'s Commands tables are a frequent drift point).

**Done-when:** both checklists pass; report findings rather than silently fixing unrelated issues
unless asked to also apply fixes.

---

## 4. Service Agent

**Purpose:** make the project runnable as a service — self-hosted (homelab) or cloud-hosted —
rather than only as a local CLI/library. **This capability does not exist in the repo yet.** No API
layer, web server, job queue, or containerization is currently present; `CONTEXT.md`'s stated
non-goals include "No GUI editor; CLI plus Python API" — a *service wrapper* around the existing
pipeline is not the same thing as a GUI editor, but it is new scope. Confirm direction with the user
before large scaffolding changes, and update `CONTEXT.md` (Non-Goals / Next Build Steps) once a
direction is chosen so it stops being tribal knowledge.

**Things this agent needs to account for, given the current architecture:**
- `ingest`, `match`, and `render` are long-running (gallery ingestion is described as "under two
  minutes" for 480 photos; larger galleries scale further) — a service needs async job handling
  (background task + status polling, or a queue), not a synchronous request/response per call.
- One DuckDB file holds one `--tile-side`; concurrent writers to the same DuckDB file are not
  something the current code is designed for (`ingest.py` does per-image transactions assuming a
  single writer). Multi-user/multi-tenant service use needs either per-user DB files or a locking
  story — don't assume concurrent-safe writes exist today.
- Large artifacts in play: the gallery itself, `mosaic.duckdb` (tens of MB+), rendered PNGs. A
  hosted service needs a storage/retention plan for these, not just the Python environment.
- The schema-versioning story ("delete and re-ingest" per `CONTEXT.md`) is fine for a single local
  user; a hosted service should decide how it surfaces a schema-version mismatch to a remote user
  who can't just delete a file by hand.
- Packaging already provides a console-script entry point (`mosaic-builder`, see
  `pyproject.toml`'s `[project.scripts]`) and `uv sync` for environment setup — reuse these rather
  than reinventing environment setup inside a container.

**Self-hosted path:** this session has the `add-hosted-server` skill available for walking through
adding a new service with a real hostname/TLS on a UniFi+Synology homelab setup — use it when the
user is deploying to their own home infrastructure rather than designing the service layer itself.

**Done-when:** a concrete architecture (API shape, job handling, storage plan) is proposed and
agreed with the user before implementation; `CONTEXT.md` is updated to reflect the decision once
made; existing CLI/library behavior and tests are untouched unless the user asks for the pipeline
itself to change.

---

## 5. Package Fit & Upstreaming Agent

**Purpose:** given a novel, bespoke implementation — one where §2 step 0 found no suitable
existing-package equivalent — assess whether it's a good candidate to contribute upstream to an
existing package, based on that package's actual stated/documented scope. Not a guess, and not an
action: this agent produces a recommendation, never opens a real upstream issue/PR itself.

**Example trigger:** `tiler.periodicity_score` (FFT-based grid/regularity concentration score, added
alongside `color_contrast_score` for fixture-vs-tiled-wall detection) has no existing-package
equivalent found so far — it's the first real candidate for this agent to evaluate.

**Process:**
1. Identify candidate target package(s) whose documented scope plausibly covers the new function
   (e.g. is a grid/periodicity detector in scope for `scikit-image`'s feature or texture modules?
   Check the package's own stated scope/docs, not just "it's a popular image library").
2. Compare the custom implementation's API shape against that package's existing conventions
   (naming, signature style, return types, input types — e.g. does it take a `numpy.ndarray` or a
   `PIL.Image`? Does it return a bare float, or something richer?).
3. Produce a recommendation:
   - **Contribute upstream** — sketch what a PR would look like and which module/file it would
     live in, referencing the target package's actual contribution docs if any exist.
   - **Keep local** — and say why (too domain-specific, too experimental/unvalidated, the target
     package isn't accepting this kind of contribution, etc.).
4. **Never open a real upstream issue/PR without explicit user approval.** This agent's output is a
   written recommendation for the user to act on, not an action taken on its own.

**Done-when:** a written recommendation (contribute vs. keep local) exists, with reasoning tied to
the target package's actual documented scope — not an assumption about what it "probably" covers.

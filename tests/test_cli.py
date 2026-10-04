"""Tests for the unified ``python -m mosaic_builder`` dispatcher."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from mosaic_builder import renderer
from mosaic_builder.matcher import load_match_result

SUBCOMMANDS = ("ingest", "preview", "match", "render", "mosaic", "validate")

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

GALLERY_COLORS = ((220, 30, 30), (30, 200, 30), (40, 40, 210))
TILE_SIDE = 16


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(SRC_DIR)}
    return subprocess.run(
        [sys.executable, "-m", "mosaic_builder", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


def _build_gallery(tmp_path: Path) -> Path:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    for index, color in enumerate(GALLERY_COLORS):
        Image.new("RGB", (64, 64), color).save(gallery / f"swatch_{index}.png")
    return gallery


def _build_target(tmp_path: Path, color: tuple[int, int, int] = (200, 40, 40)) -> Path:
    target = tmp_path / "target.png"
    Image.new("RGB", (64, 64), color).save(target)
    return target


def _ingest(tmp_path: Path) -> Path:
    gallery = _build_gallery(tmp_path)
    db_path = tmp_path / "tiles.duckdb"
    result = _run_cli(
        "ingest",
        str(gallery),
        "--db",
        str(db_path),
        "--tile-side",
        str(TILE_SIDE),
        "--no-progress",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    return db_path


def test_top_level_help_lists_every_subcommand(tmp_path: Path):
    result = _run_cli("--help", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    for name in SUBCOMMANDS:
        assert name in result.stdout


@pytest.mark.parametrize("name", SUBCOMMANDS)
def test_each_subcommand_accepts_help(name: str, tmp_path: Path):
    result = _run_cli(name, "--help", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()


def test_mosaic_end_to_end(tmp_path: Path):
    db_path = _ingest(tmp_path)
    target = _build_target(tmp_path)
    out_path = tmp_path / "mosaic.png"

    result = _run_cli(
        "mosaic",
        str(target),
        "--db",
        str(db_path),
        "--grain",
        "16",
        "--out",
        str(out_path),
        "--no-progress",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert out_path.exists()
    with Image.open(out_path) as image:
        assert image.size == (4 * TILE_SIDE, 4 * TILE_SIDE)


def test_mosaic_missing_target_reports_friendly_error(tmp_path: Path):
    db_path = _ingest(tmp_path)
    result = _run_cli(
        "mosaic",
        str(tmp_path / "nope.png"),
        "--db",
        str(db_path),
        "--grain",
        "16",
        "--out",
        str(tmp_path / "mosaic.png"),
        "--no-progress",
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr + result.stdout


def test_keep_match_agrees_with_rendering_the_saved_json(tmp_path: Path):
    db_path = _ingest(tmp_path)
    target = _build_target(tmp_path)
    out_path = tmp_path / "mosaic.png"
    match_path = tmp_path / "match.json"

    result = _run_cli(
        "mosaic",
        str(target),
        "--db",
        str(db_path),
        "--grain",
        "16",
        "--out",
        str(out_path),
        "--keep-match",
        str(match_path),
        "--no-progress",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert match_path.exists()

    saved = load_match_result(match_path)
    assert len(saved.matches) == saved.rows * saved.cols

    from_json = tmp_path / "from_json.png"
    renderer.run_render(match_path, db_path, from_json, show_progress=False)

    with Image.open(out_path) as in_memory, Image.open(from_json) as round_tripped:
        assert in_memory.size == round_tripped.size
        assert in_memory.convert("RGB").tobytes() == round_tripped.convert("RGB").tobytes()

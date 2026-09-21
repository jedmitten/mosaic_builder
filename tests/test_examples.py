"""Tests for the committed showcase example (examples/output/).

These run anywhere, with no gallery and no database, against the files
already committed to the repository. If the showcase has not been generated
yet (a fresh clone before notebooks/visual_demo.ipynb Section 10 has run),
the whole module is skipped rather than failing.
"""

import json
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "examples" / "output"
SIDECAR_PATH = OUTPUT_DIR / "urinal_showcase.json"

if not SIDECAR_PATH.exists():
    pytest.skip(
        f"showcase not generated yet: {SIDECAR_PATH} is missing "
        "(run notebooks/visual_demo.ipynb Section 10 with the full gallery ingested)",
        allow_module_level=True,
    )

SUMMARY = json.loads(SIDECAR_PATH.read_text())

MOSAIC_CEILING_BYTES = 7 * 1024 * 1024
COMPARISON_CEILING_BYTES = 1 * 1024 * 1024
TARGET_CEILING_BYTES = 2 * 1024 * 1024

REQUIRED_KEYS = {
    "target",
    "target_size",
    "grain",
    "tile_side",
    "max_reuse",
    "min_repeat_dist",
    "blend",
    "rows",
    "cols",
    "mosaic_size",
    "mean_delta_e",
    "distinct_tiles",
    "gallery_images",
    "gallery_tiles",
    "cli",
}


def test_sidecar_has_every_required_key():
    assert REQUIRED_KEYS <= SUMMARY.keys()


def test_mosaic_size_matches_grid_times_tile_side():
    expected = [SUMMARY["cols"] * SUMMARY["tile_side"], SUMMARY["rows"] * SUMMARY["tile_side"]]
    assert SUMMARY["mosaic_size"] == expected

    mosaic_path = OUTPUT_DIR / "urinal_mosaic.png"
    assert mosaic_path.exists()
    with Image.open(mosaic_path) as img:
        assert list(img.size) == expected


def test_grid_dimensions_match_target_size_and_grain():
    target_w, target_h = SUMMARY["target_size"]
    grain = SUMMARY["grain"]
    assert SUMMARY["rows"] == target_h // grain
    assert SUMMARY["cols"] == target_w // grain


def test_normalized_target_exists_and_is_within_size_limit():
    target_path = ROOT / SUMMARY["target"]
    assert target_path.exists()
    with Image.open(target_path) as img:
        assert max(img.size) <= 1024


def test_comparison_image_exists_and_is_within_width_limit():
    comparison_path = OUTPUT_DIR / "urinal_comparison.png"
    assert comparison_path.exists()
    with Image.open(comparison_path) as img:
        assert img.size[0] <= 1600


def test_every_committed_file_is_under_its_size_ceiling():
    target_path = ROOT / SUMMARY["target"]
    mosaic_path = OUTPUT_DIR / "urinal_mosaic.png"
    comparison_path = OUTPUT_DIR / "urinal_comparison.png"

    assert target_path.stat().st_size < TARGET_CEILING_BYTES
    assert mosaic_path.stat().st_size < MOSAIC_CEILING_BYTES
    assert comparison_path.stat().st_size < COMPARISON_CEILING_BYTES


def test_cli_command_reflects_the_recorded_parameters():
    cli = SUMMARY["cli"]
    assert f"--grain {SUMMARY['grain']}" in cli
    assert f"--max-reuse {SUMMARY['max_reuse']}" in cli
    assert f"--min-repeat-dist {SUMMARY['min_repeat_dist']}" in cli
    assert SUMMARY["target"] in cli

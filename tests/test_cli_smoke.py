import subprocess
import sys

from tests.utils import solid


def test_cli_quick_smoke(tmp_path):
    ref = solid(24, 24, (200, 50, 50))
    ref_path = tmp_path / "ref.png"
    ref.save(ref_path)
    tiles_dir = tmp_path / "tiles"
    tiles_dir.mkdir()
    for i, c in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        solid(24, 24, c).save(tiles_dir / f"t{i}.png")
    out = tmp_path / "out.png"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mosaic_builder.cli",
            "quick",
            "--ref",
            str(ref_path),
            "--tiles",
            str(tiles_dir),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists() and out.stat().st_size > 100

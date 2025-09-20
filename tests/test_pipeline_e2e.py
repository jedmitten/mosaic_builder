from mosaic_builder.pipeline import quick
from tests.utils import solid


def test_quick_end_to_end(tmp_path):
    ref = solid(48, 48, (255, 0, 0))
    tiles_dir = tmp_path / "tiles"
    tiles_dir.mkdir()
    for name, rgb in [
        ("red", (255, 0, 0)),
        ("pink", (255, 128, 128)),
        ("blue", (0, 0, 255)),
    ]:
        solid(32, 24, rgb).save(tiles_dir / f"{name}.png")
    ref_path = tmp_path / "ref.png"
    out_path = tmp_path / "out.png"
    ref.save(ref_path)
    quick(str(ref_path), str(tiles_dir), str(out_path), tile_side=12)
    assert out_path.exists() and out_path.stat().st_size > 100

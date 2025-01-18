from mosaic_builder.collection import is_image
from pathlib import Path


def test_is_image(gallery_files):
    assert is_image(Path(gallery_files[0])) is True
    assert is_image(Path(__file__)) is False

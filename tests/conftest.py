from pathlib import Path
import pytest
import cv2


def get_project_root() -> Path:
    return Path(__file__).parent.parent


@pytest.fixture
def gallery():
    return Path(get_project_root() / "gallery/Views from the urinal")


@pytest.fixture
def gallery_files(gallery):
    return list(gallery.glob("*"))


@pytest.fixture
def image_02(gallery_files):
    return cv2.imread(gallery_files[0])

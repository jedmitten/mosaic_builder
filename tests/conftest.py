from pathlib import Path
import pytest


def get_project_root() -> Path:
    return Path(__file__).parent.parent


@pytest.fixture
def gallery():
    return Path(get_project_root() / "gallery/Views from the urinal")


@pytest.fixture
def gallery_files(gallery):
    return list(gallery.glob("*"))

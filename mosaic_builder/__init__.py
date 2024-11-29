from pathlib import Path
from . import collection


def get_gallery_dir():
    my_dir = Path(__file__).parent.parent
    return my_dir / "gallery"
    
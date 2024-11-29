from pathlib import Path
import os

from PIL import Image


def fetch_image_files_from_path(file_path: Path) -> list[Path]:
    if not file_path.exists():
        raise FileNotFoundError("The specified path could not be found: " + str(file_path))

    if not file_path.is_dir():
        raise RuntimeError("The path specified is not a directory: " + str(file_path))

    paths = []
    for x in file_path.walk():
        with open(x, 'rb') as image_file:
            if Image.verify(image_file):
                paths.append(x)
    return paths

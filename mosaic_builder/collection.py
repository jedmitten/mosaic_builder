from pathlib import Path
import os

import puremagic


def is_image(file_path: Path | str) -> bool:
    if isinstance(file_path, str):
        file_path = Path(file_path)
    if not (file_path.exists() and file_path.is_file()):
        raise FileNotFoundError(
            "The specified path could not be found: " + str(file_path)
        )
    mime_base = puremagic.magic_file(file_path)[0].mime_type.split("/")[0]
    return mime_base.lower() == "image"


def fetch_image_files_from_path(file_path: Path) -> list[Path]:
    if isinstance(file_path, str):
        file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(
            "The specified path could not be found: " + str(file_path)
        )

    if not file_path.is_dir():
        raise RuntimeError("The path specified is not a directory: " + str(file_path))

    paths = []
    for x in file_path.glob("*"):
        with open(x, "rb") as image_file:
            if is_image(image_file):
                paths.append(x)
    return paths


if __name__ == "__main__":
    path = Path(os.getcwd())
    print(fetch_image_files_from_path(path / "gallery/Views from the urinal"))

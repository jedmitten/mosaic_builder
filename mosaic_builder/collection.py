from dataclasses import dataclass
from pathlib import Path
import numpy as np
import cv2
from typing import Iterator, Union
import os

import puremagic


@dataclass
class ImageHolder:
    file_path: Union[Path, None]
    image_data: Union[bytes, np.ndarray]

    def __post_init__(self):
        if self.file_path:
            if not self.file_path.exists():
                raise FileNotFoundError(f"Path not found: {self.file_path}")
            if not self.file_path.is_file():
                raise RuntimeError(f"Not a file: {self.file_path}")
            if isinstance(self.image_data, bytes):
                # Load from file if bytes not provided
                self.image_data = cv2.imread(str(self.file_path))

        if not isinstance(self.image_data, (bytes, np.ndarray)):
            raise TypeError("image_data must be bytes or numpy array")

    def __repr__(self):
        data_type = "bytes" if isinstance(self.image_data, bytes) else "array"
        if isinstance(self.image_data, np.ndarray):
            size = f"{self.image_data.shape}"
        else:
            size = f"{len(self.image_data)} bytes"
        return (
            f"ImageHolder(file_path={self.file_path}, image_data={data_type}[{size}])"
        )


@dataclass
class ImageHolderCollection:
    images: list[ImageHolder]


def is_image(file_path: Path | str) -> bool:
    if isinstance(file_path, str):
        file_path = Path(file_path)
    if not (file_path.exists() and file_path.is_file()):
        raise FileNotFoundError(
            "The specified path could not be found: " + str(file_path)
        )
    mime_base = puremagic.magic_file(file_path)[0].mime_type.split("/")[0]
    return mime_base.lower() == "image"


def path_to_image_holder(file_path: Path) -> Iterator[ImageHolder]:
    if isinstance(file_path, str):
        file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(
            "The specified path could not be found: " + str(file_path)
        )

    if not file_path.is_file():
        raise RuntimeError("The path specified is not a file: " + str(file_path))

    with open(file_path, "rb") as image_file:
        if is_image(image_file):
            yield ImageHolder(file_path=image_file, image_data=cv2.imread(image_file))


def dir_to_image_holder_collection(dir_path: Path) -> Iterator[Path]:
    for x in dir_path.glob("*"):
        yield path_to_image_holder(x)

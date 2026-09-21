"""Target image analysis for mosaic matching.

Turns a target image into a grid of per-cell LAB colour descriptors that
can later be matched against tile descriptors from the DuckDB store.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image

from .tiler import _srgb_to_lab


@dataclass(frozen=True)
class CellDescriptor:
    row: int
    col: int
    lab: tuple[float, float, float]


@dataclass(frozen=True)
class TargetGrid:
    rows: int
    cols: int
    grain: int
    cells: list[CellDescriptor]


def analyze_target(image: Image.Image, *, grain: int) -> TargetGrid:
    """Divide a target image into a grid of cells and compute each cell's mean LAB color.

    `grain` is the edge length of one grid cell in target-image pixels.
    `rows = height // grain` and `cols = width // grain`; any remainder of
    pixels on the right and/or bottom edge (when the image dimensions are
    not exact multiples of `grain`) is dropped.

    Raises `ValueError` if the image is smaller than one cell in either
    dimension (i.e. `rows` or `cols` would be 0).
    """
    rgb_image = image.convert("RGB")
    width, height = rgb_image.size
    rows = height // grain
    cols = width // grain
    if rows == 0 or cols == 0:
        raise ValueError(
            f"Image size {width}x{height} is too small for grain={grain} (computed rows={rows}, cols={cols})"
        )

    arr = np.asarray(rgb_image, dtype=np.uint8)
    lab = _srgb_to_lab(arr)

    cropped = lab[: rows * grain, : cols * grain, :]
    blocks = cropped.reshape(rows, grain, cols, grain, 3)
    means = blocks.mean(axis=(1, 3))

    cells = [
        CellDescriptor(row=r, col=c, lab=tuple(float(v) for v in means[r, c]))
        for r in range(rows)
        for c in range(cols)
    ]

    return TargetGrid(rows=rows, cols=cols, grain=grain, cells=cells)

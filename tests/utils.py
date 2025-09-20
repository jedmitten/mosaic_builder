from __future__ import annotations

import hashlib
import io

import numpy as np
from PIL import Image
from skimage.color import rgb2lab


def solid(w: int, h: int, rgb: tuple[int, int, int]) -> Image.Image:
    arr = np.full((h, w, 3), rgb, dtype=np.uint8)
    return Image.fromarray(arr, "RGB")


def png_md5(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return hashlib.md5(buf.getvalue()).hexdigest()


def mean_lab(im: Image.Image) -> tuple[float, float, float]:
    rgb = np.asarray(im, dtype=np.uint8) / 255.0
    L, a, b = rgb2lab(rgb).reshape(-1, 3).mean(0)
    return float(L), float(a), float(b)


def delta_e_mean(im_a: Image.Image, im_b: Image.Image) -> float:
    a = np.asarray(im_a, dtype=np.uint8) / 255.0
    b = np.asarray(im_b, dtype=np.uint8) / 255.0
    lab_a = rgb2lab(a).reshape(-1, 3)
    lab_b = rgb2lab(b).reshape(-1, 3)
    diff = lab_a - lab_b
    return float(np.linalg.norm(diff, axis=1).mean())

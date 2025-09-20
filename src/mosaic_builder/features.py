import numpy as np
from PIL import Image

from .color import mean_lab


def descriptor_mean_lab(img: Image.Image) -> np.ndarray:
    L, a, b = mean_lab(np.asarray(img, dtype=np.uint8))
    return np.array([L, a, b], dtype=np.float32)

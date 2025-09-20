import numpy as np
from skimage import color as skcolor


def rgb_to_lab(rgb_uint8: np.ndarray) -> np.ndarray:
    rgb = rgb_uint8.astype(np.float32) / 255.0
    return skcolor.rgb2lab(rgb)


def mean_lab(rgb_uint8: np.ndarray) -> tuple[float, float, float]:
    lab = rgb_to_lab(rgb_uint8)
    m = lab.reshape(-1, 3).mean(axis=0)
    return float(m[0]), float(m[1]), float(m[2])

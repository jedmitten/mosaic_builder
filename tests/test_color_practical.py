import numpy as np
from PIL import Image

from mosaic_builder.color import mean_lab


def test_white_black_landmarks():
    white = Image.new("RGB", (2, 2), (255, 255, 255))
    black = Image.new("RGB", (2, 2), (0, 0, 0))
    Lw, aw, bw = mean_lab(np.asarray(white, np.uint8))
    Lb, ab, bb = mean_lab(np.asarray(black, np.uint8))
    assert Lw > 99 and abs(aw) < 1 and abs(bw) < 1
    assert Lb < 1 and abs(ab) < 1 and abs(bb) < 1

import numpy as np

from mosaic_builder import image_stats


def test_get_image_dims(image_02, show_images, debug_show):
    dims = image_stats.get_image_dims(image_02)
    assert dims == (4080, 3072)  # found by checking dims previously


def test_get_image_color_weight_shape(sample_image, show_images, debug_show):
    weights = image_stats.get_image_color_weight(sample_image)
    assert weights.shape == (8, 8, 8)


def test_get_image_color_weight_known_values(
    known_color_image, show_images, debug_show
):
    weights = image_stats.get_image_color_weight(known_color_image)

    # Test shape
    assert weights.shape == (8, 8, 8)

    # Test total pixels
    assert np.sum(weights) == 4  # 2x2 image = 4 pixels

    # Test specific color locations
    # Convert 256 colors to 8 bins (256/8 = 32 per bin)
    # Pure colors will be in last bin (index 7)
    assert weights[0, 0, 7] == 1  # pure blue
    assert weights[0, 7, 0] == 1  # pure green
    assert weights[7, 0, 0] == 1  # pure red
    assert weights[7, 7, 7] == 1  # white

from mosaic_builder import image_stats


def test_get_image_dims(image_02):
    dims = image_stats.get_image_dims(image_02)
    assert dims == (4080, 3072)  # found by checking dims previously

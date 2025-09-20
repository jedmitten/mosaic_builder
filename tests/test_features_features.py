from mosaic_builder.features import descriptor_mean_lab
from tests.utils import solid


def test_descriptor_tracks_color_direction():
    red = solid(8, 8, (255, 0, 0))
    blue = solid(8, 8, (0, 0, 255))
    d_red = descriptor_mean_lab(red)
    d_blue = descriptor_mean_lab(blue)
    assert d_red.shape == (3,)
    assert d_red[1] > 40
    assert abs(d_blue[2]) > 20  # b* magnitude significant

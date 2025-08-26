from pathlib import Path

import cv2
import numpy as np
import pytest


def get_project_root() -> Path:
    return Path(__file__).parent.parent


def show_debug_image(image, name="Test Image", delay_ms=500):
    """Display image for debugging with fixed delay."""
    cv2.imshow(name, image)
    cv2.waitKey(delay_ms)
    cv2.destroyAllWindows()


@pytest.fixture
def debug_show():
    """Fixture to provide debug image display function."""
    return show_debug_image


def pytest_addoption(parser):
    parser.addoption(
        "--show-images",
        action="store_true",
        default=False,
        help="Show test images during test execution",
    )


@pytest.fixture
def show_images(request):
    return request.config.getoption("--show-images")


@pytest.fixture
def gallery():
    return Path(get_project_root() / "gallery/Views from the urinal")


@pytest.fixture
def gallery_files(gallery):
    return list(gallery.glob("*"))


@pytest.fixture
def image_02(gallery_files):
    return cv2.imread(gallery_files[0])


@pytest.fixture
def known_color_image():
    # Create 2x2 image with known colors
    img = np.zeros((2, 2, 3), dtype=np.uint8)
    # Set pixels to known values
    img[0, 0] = [0, 0, 255]  # pure blue
    img[0, 1] = [0, 255, 0]  # pure green
    img[1, 0] = [255, 0, 0]  # pure red
    img[1, 1] = [255, 255, 255]  # white
    return img

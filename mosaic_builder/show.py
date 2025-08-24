import cv2
from PIL import Image
from pathlib import Path
from typing import Union
import click

from mosaic_builder.collection import fetch_image_files_from_path
from mosaic_builder import modify, image_stats


@click.group()
def cli():
    """Mosaic Builder CLI tools."""
    pass


def display_image(
    image_path: str | Path, window_name: str = "Image", add_text: str = ""
) -> None:
    """Display an image using OpenCV or PIL.

    Args:
        image_path: Path to image file
        window_name: Name of the window (default: "Image")
    """
    if isinstance(image_path, str):
        image_path = Path(image_path)

    # OpenCV method
    img = cv2.imread(str(image_path))
    if add_text:
        modify.add_text(img, add_text)

    cv2.imshow(window_name, img)
    cv2.waitKey(0)  # Wait for key press
    cv2.destroyAllWindows()


@cli.command()
@click.argument("image_path", type=click.Path(exists=True))
@click.option("--window-name", "-w", default="Image", help="Window name for display")
def show_image(image_path: str, window_name: str):
    img_weight = image_stats.get_image_color_weight(image_path)
    text += "Press any key to close"
    display_image(image_path, window_name, add_text="Press any key to close")


if __name__ == "__main__":
    cli()

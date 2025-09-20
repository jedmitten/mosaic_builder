from collections.abc import Mapping

from PIL import Image

from .matcher import Match


def render_mosaic(
    matches: list[Match],
    tile_images: Mapping[str, Image.Image],
    canvas_size: tuple[int, int],
    tile_side: int,
) -> Image.Image:
    canvas = Image.new("RGB", canvas_size, (0, 0, 0))
    for m in matches:
        canvas.paste(tile_images[m.tile_id], box=(m.x, m.y))
    return canvas

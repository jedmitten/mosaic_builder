from PIL import Image, ImageDraw


def side_by_side(pairs: list[tuple[str, Image.Image]]) -> Image.Image:
    w = sum(im.width for _, im in pairs)
    h = max(im.height for _, im in pairs) + 18
    canvas = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    x = 0
    for label, im in pairs:
        canvas.paste(im, (x, 18))
        draw.text((x + 4, 2), label, fill=(0, 0, 0))
        x += im.width
    return canvas

from PIL import Image, ImageOps


def make_tile(img: Image.Image, side: int = 24) -> Image.Image:
    img = ImageOps.exif_transpose(img).convert("RGB")
    return ImageOps.fit(img, (side, side), method=Image.Resampling.LANCZOS)

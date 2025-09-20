from pathlib import Path

import joblib
import numpy as np
from PIL import Image, ImageOps
from skimage.color import rgb2lab

from mosaic_builder.stores.base import BaseTileStore


def grid_avg_lab(img, tile_w: int, tile_h: int):
    w, h = img.size
    cols, rows = w // tile_w, h // tile_h
    small = img.resize((cols, rows), Image.Resampling.LANCZOS)
    arr = np.asarray(small.convert("RGB"), dtype=np.float32) / 255.0
    return rgb2lab(arr), cols, rows, small


def build_mosaic(
    store: BaseTileStore,
    index_path: Path,
    source_image: Image.Image,
    out_path: Path,
    tile_w=24,
    tile_h=24,
    debug_dir: Path | None = None,
):
    """Build a mosaic image from an input image using tiles from the store."""
    print(f"[DEBUG] Loading index from: {index_path}")
    bundle = joblib.load(index_path)
    ids, tree = bundle["ids"], bundle["tree"]

    print(f"[DEBUG] Processing source image with size: {source_image.size}")
    lab_grid, cols, rows, small = grid_avg_lab(source_image, tile_w, tile_h)

    print(f"[DEBUG] Mosaic grid dimensions: {cols}x{rows}")

    nearest_ids = np.empty((rows, cols), dtype=np.int32)
    for y in range(rows):
        d, idx = tree.query(lab_grid[y, :, :], k=1)
        nearest_ids[y, :] = ids[idx]

    print("[DEBUG] Assembling mosaic...")
    try:
        canvas = Image.new("RGB", (cols * tile_w, rows * tile_h))
        for y in range(rows):
            for x in range(cols):
                path, gx, gy, tw, th = store.tile_patch_info(int(nearest_ids[y, x]))
                print(f"[DEBUG] Using tile from: {path}")
                im = ImageOps.exif_transpose(Image.open(path).convert("RGB"))
                patch = im.crop((gx * tw, gy * th, (gx + 1) * tw, (gy + 1) * th))
                canvas.paste(
                    patch.resize((tile_w, tile_h), Image.Resampling.LANCZOS),
                    (x * tile_w, y * tile_h),
                )
        print(f"[DEBUG] Saving mosaic to: {out_path}")
        canvas.save(out_path)
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            small.save(debug_dir / "target_colorgrid.jpg")
            canvas.save(debug_dir / "mosaic_preview.jpg")
    finally:
        store.close()

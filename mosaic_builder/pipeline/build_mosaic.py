from pathlib import Path

import joblib
import numpy as np
from PIL import Image, ImageOps
from skimage.color import rgb2lab

from mosaic_builder.stores.factory import open_store


def grid_avg_lab(img, tile_w: int, tile_h: int):
    w, h = img.size
    cols, rows = w // tile_w, h // tile_h
    small = img.resize((cols, rows), Image.Resampling.LANCZOS)
    arr = np.asarray(small.convert("RGB"), dtype=np.float32) / 255.0
    return rgb2lab(arr), cols, rows, small


def build_mosaic(
    store_url: str,
    index_path: Path,
    target_path: Path,
    out_path: Path,
    tile_w=24,
    tile_h=24,
    debug_dir: Path | None = None,
):
    bundle = joblib.load(index_path)
    ids, tree = bundle["ids"], bundle["tree"]

    target = ImageOps.exif_transpose(Image.open(target_path).convert("RGB"))
    lab_grid, cols, rows, small = grid_avg_lab(target, tile_w, tile_h)

    nearest_ids = np.empty((rows, cols), dtype=np.int32)
    for y in range(rows):
        d, idx = tree.query(lab_grid[y, :, :], k=1)
        nearest_ids[y, :] = ids[idx]

    store = open_store(store_url)
    try:
        canvas = Image.new("RGB", (cols * tile_w, rows * tile_h))
        for y in range(rows):
            for x in range(cols):
                path, gx, gy, tw, th = store.tile_patch_info(int(nearest_ids[y, x]))
                im = ImageOps.exif_transpose(Image.open(path).convert("RGB"))
                patch = im.crop((gx * tw, gy * th, (gx + 1) * tw, (gy + 1) * th))
                canvas.paste(
                    patch.resize((tile_w, tile_h), Image.Resampling.LANCZOS),
                    (x * tile_w, y * tile_h),
                )
        canvas.save(out_path)
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            small.save(debug_dir / "target_colorgrid.jpg")
            canvas.save(debug_dir / "mosaic_preview.jpg")
    finally:
        store.close()

from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
from skimage.color import rgb2lab
from mosaic_builder.stores.factory import open_store


def avg_lab_from_patch(pil_img):
    arr = np.asarray(pil_img.convert("RGB"), dtype=np.float32) / 255.0
    lab = rgb2lab(arr)
    return lab.reshape(-1, 3).mean(axis=0)


def ingest_dir(
    store_url: str,
    images_dir: Path,
    tile_w=24,
    tile_h=24,
    debug_dir: Path | None = None,
):
    store = open_store(store_url)
    store.ensure_schema()
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
    try:
        for p in sorted(images_dir.rglob("*")):
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            im = ImageOps.exif_transpose(Image.open(p).convert("RGB"))
            w, h = im.size
            photo_id = store.upsert_photo(p, w, h)

            cols, rows = w // tile_w, h // tile_h
            batch = []
            thumbs = Image.new("RGB", (cols * tile_w, rows * tile_h))
            for y in range(rows):
                for x in range(cols):
                    box = (x * tile_w, y * tile_h, (x + 1) * tile_w, (y + 1) * tile_h)
                    patch = im.crop(box)
                    L, A, B = avg_lab_from_patch(patch)
                    batch.append(
                        (photo_id, x, y, tile_w, tile_h, float(L), float(A), float(B))
                    )
                    # optional montage
                    thumbs.paste(
                        patch.resize((tile_w, tile_h)), (x * tile_w, y * tile_h)
                    )
            if batch:
                store.insert_tiles(batch)
            if debug_dir:
                thumbs.save(debug_dir / f"{p.stem}_tiles.jpg")
    finally:
        store.close()

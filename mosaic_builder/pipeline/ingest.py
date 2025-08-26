from pathlib import Path

import numpy as np
from PIL import Image as PILImage
from PIL import ImageOps
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from skimage.color import rgb2lab

from mosaic_builder.stores.factory import open_store


def avg_lab_from_patch(pil_img):
    arr = np.asarray(pil_img.convert("RGB"), dtype=np.float32) / 255.0
    lab = rgb2lab(arr)
    return lab.reshape(-1, 3).mean(axis=0)


def ingest_dir(
    store_url: str, images_dir: Path, tile_w=24, tile_h=24, debug_dir: Path | None = None, reingest: bool = False
):
    images = [p for p in sorted(images_dir.rglob("*")) if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    if not images:
        print(f"No images found under {images_dir}")
        return

    store = open_store(store_url)
    store.ensure_schema()
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)

    photos_total = 0
    tiles_total = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}[/bold]"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
    ) as progress:
        files_task = progress.add_task("Photos", total=len(images))
        for p in images:
            im = ImageOps.exif_transpose(PILImage.open(p).convert("RGB"))
            w, h = im.size
            photo_id = store.upsert_photo(p, w, h)

            cols, rows = w // tile_w, h // tile_h
            grid_id = store.upsert_grid(photo_id, tile_w, tile_h, cols, rows)

            # Skip or force reingest per grid
            if store.has_tiles_for_grid(grid_id) and not reingest:
                progress.update(files_task, advance=1, description="Photos (skipping)")
                continue
            if reingest:
                store.delete_tiles_for_grid(grid_id)

            total_tiles = cols * rows
            per_file = progress.add_task(f"Tiling {p.name} ({cols}×{rows})", total=total_tiles)

            rows_to_insert: list[tuple[int, int, float, float, float]] = []
            thumbs = PILImage.new("RGB", (cols * tile_w, rows * tile_h)) if (debug_dir and cols and rows) else None

            for y in range(rows):
                for x in range(cols):
                    box = (x * tile_w, y * tile_h, (x + 1) * tile_w, (y + 1) * tile_h)
                    patch = im.crop(box)
                    L, A, B = avg_lab_from_patch(patch)
                    rows_to_insert.append((x, y, float(L), float(A), float(B)))
                    if thumbs:
                        thumbs.paste(patch.resize((tile_w, tile_h)), (x * tile_w, y * tile_h))
                    progress.update(per_file, advance=1)

            if rows_to_insert:
                store.insert_tiles(grid_id, rows_to_insert)

            progress.update(files_task, advance=1)
            progress.remove_task(per_file)
            if thumbs:
                thumbs.save((debug_dir / f"{p.stem}_tiles_{tile_w}x{tile_h}.jpg"))

    store.close()
    print(f"[mosaic-builder] Ingest complete: {photos_total} new photos, {tiles_total} tiles added.")

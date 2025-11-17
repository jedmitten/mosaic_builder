"""DuckDB ingestion helpers for mosaic tiles."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
from PIL import Image, ImageOps

from .duckdb_store import ensure_schema, open_database
from .tiler import (
    extract_character_tiles,
    iter_gallery_images,
    load_image,
    mean_rgb,
    resize_tile,
    tile_png_bytes,
)


@dataclass(frozen=True)
class TilePreview:
    label: str
    coverage: float
    score: float
    data_url: str


@dataclass(frozen=True)
class ImagePreview:
    path: str
    width: int
    height: int
    original_data_url: str
    tiles: list[TilePreview]


def _image_to_data_url(img: Image.Image) -> str:
    buf = tile_png_bytes(img)
    encoded = base64.b64encode(buf).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _insert_image(conn: duckdb.DuckDBPyConnection, path: Path, img: Image.Image) -> int:
    w, h = img.size
    conn.execute("DELETE FROM images WHERE path = ?", [str(path)])
    next_id = conn.execute("SELECT COALESCE(MAX(image_id), 0) + 1 FROM images").fetchone()[0]
    conn.execute(
        "INSERT INTO images (image_id, path, width, height) VALUES (?, ?, ?, ?)",
        [int(next_id), str(path), w, h],
    )
    return int(next_id)


def _insert_tile(
    conn: duckdb.DuckDBPyConnection,
    image_id: int,
    idx: int,
    crop_box: tuple[int, int, int, int],
    coverage: float,
    score: float,
    tile: Image.Image,
) -> None:
    r, g, b = [float(v) for v in mean_rgb(tile)]
    coverage = float(coverage)
    score = float(score)
    descriptor = np.array([r, g, b], dtype=np.float32).tobytes()
    conn.execute(
        """
        INSERT OR REPLACE INTO tiles
        (image_id, tile_index, crop_box, coverage, score, mean_r, mean_g, mean_b, descriptor, tile_png)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            image_id,
            idx,
            ",".join(map(str, crop_box)),
            coverage,
            score,
            r,
            g,
            b,
            descriptor,
            tile_png_bytes(tile),
        ],
    )


def ingest_gallery(
    images_dir: Path,
    db_path: Path,
    *,
    tile_side: int = 48,
    max_tiles: int = 3,
    show_progress: bool = True,
) -> list[ImagePreview]:
    """Ingest a gallery directory and return previews for inspection."""
    conn = open_database(db_path)
    ensure_schema(conn)
    previews: list[ImagePreview] = []
    progress_iter = _iter_with_progress(
        iter_gallery_images(images_dir), desc="Ingesting images", enabled=show_progress
    )
    try:
        for image_path in progress_iter:
            base = load_image(image_path)
            image_id = _insert_image(conn, image_path, base)
            tiles = []
            raw_tiles = extract_character_tiles(base, max_tiles=max_tiles)
            for idx, tile_crop in enumerate(raw_tiles):
                resized = resize_tile(tile_crop.image, tile_side)
                coverage = float(
                    (tile_crop.image.width * tile_crop.image.height) / (base.width * base.height)
                )
                score = float(tile_crop.score)
                _insert_tile(
                    conn,
                    image_id=image_id,
                    idx=idx,
                    crop_box=tile_crop.box,
                    coverage=coverage,
                    score=score,
                    tile=resized,
                )
                tiles.append(
                    TilePreview(
                        label=f"{image_path.stem}#{idx + 1}",
                        coverage=coverage,
                        score=score,
                        data_url=_image_to_data_url(resized),
                    )
                )
            previews.append(
                ImagePreview(
                    path=str(image_path),
                    width=base.width,
                    height=base.height,
                    original_data_url=_image_to_data_url(_preview_image(base)),
                    tiles=tiles,
                )
            )
    finally:
        conn.close()
    return previews


def _preview_image(img: Image.Image, max_side: int = 320) -> Image.Image:
    if max(img.size) <= max_side:
        return img
    return ImageOps.contain(img, (max_side, max_side))


def _iter_with_progress(items, desc: str, enabled: bool):
    sequence = list(items)
    total = len(sequence)
    if not enabled or total == 0:
        for item in sequence:
            yield item
        return

    bar_width = 30
    print(f"{desc}: starting ({total} items)")
    for idx, item in enumerate(sequence, 1):
        filled = int(bar_width * idx / total)
        bar = "#" * filled + "-" * (bar_width - filled)
        print(f"\r{desc}: [{bar}] {idx}/{total}", end="", flush=True)
        yield item
    print()

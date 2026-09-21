"""HTML preview generation — reads tiles from the database."""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

from .duckdb_store import (
    ensure_schema,
    get_all_images,
    get_tiles_for_image,
    open_database,
)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Mosaic Builder Preview</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #111; color: #f5f5f5; margin: 0; padding: 1rem; }}
    h1 {{ margin-top: 0; }}
    .image-block {{ border: 1px solid #333; border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; background: #1c1c1c; }}
    .tiles {{ display: flex; gap: 1rem; overflow-x: auto; padding: 0.5rem 0; }}
    .tile-card {{ min-width: 160px; background: #222; border-radius: 6px; padding: 0.5rem; text-align: center; }}
    .tile-card img {{ width: 100%; border-radius: 4px; }}
    .meta {{ font-size: 0.85rem; color: #bbb; }}
  </style>
</head>
<body>
  <h1>Mosaic Builder Preview</h1>
  {blocks}
</body>
</html>
"""


def _tile_data_url(tile_png: bytes) -> str:
    encoded = base64.b64encode(tile_png).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _render_block(image: dict, tiles: list[dict]) -> str:
    tiles_html = "\n".join(
        f"""<div class="tile-card">
        <img src="{_tile_data_url(tile["tile_png"])}" alt="tile {tile["tile_index"]}" />
        <div class="meta">#{tile["tile_index"] + 1}<br/>{tile["tile_side"]}px<br/>coverage {tile["coverage"]:.2f}<br/>score {tile["score"]:.2f}</div>
      </div>"""
        for tile in tiles
    )
    return f"""
    <section class="image-block">
      <div class="meta">{image["path"]} — {image["width"]}×{image["height"]}</div>
      <div class="tiles">
        {tiles_html}
      </div>
    </section>
    """


def render_preview(
    db_path: Path, output_path: Path, *, first_n: int | None = None, random_n: int | None = None
) -> Path:
    """Read images and tiles from the DB and render an HTML preview."""
    conn = open_database(db_path)
    ensure_schema(conn)
    try:
        images = get_all_images(conn)
        if first_n is not None:
            images = images[: max(0, first_n)]
        elif random_n is not None:
            import random
            from time import time_ns

            rng = random.Random(time_ns())
            k = min(random_n, len(images))
            images = rng.sample(images, k=k)

        blocks = []
        for img in images:
            tiles = get_tiles_for_image(conn, img["image_id"])
            blocks.append(_render_block(img, tiles))
    finally:
        conn.close()

    html = HTML_TEMPLATE.format(blocks="\n".join(blocks))
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a preview HTML from the mosaic database.")
    parser.add_argument("--db", type=Path, default=Path("mosaic.duckdb"))
    parser.add_argument("--out", type=Path, default=Path("preview.html"))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--first-n", type=int, help="Show only the first N images")
    group.add_argument("--random-n", type=int, help="Show random N images")
    args = parser.parse_args()

    render_preview(args.db, args.out, first_n=args.first_n, random_n=args.random_n)
    print(f"Wrote preview to {args.out}")


if __name__ == "__main__":
    main()

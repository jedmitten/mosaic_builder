"""HTML preview generation for galleries."""

from __future__ import annotations

import argparse
from pathlib import Path

from .ingest import ImagePreview, ingest_gallery


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Mosaic Builder Preview</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #111; color: #f5f5f5; margin: 0; padding: 1rem; }}
    h1 {{ margin-top: 0; }}
    .image-block {{ border: 1px solid #333; border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; background: #1c1c1c; }}
    .original {{ width: 240px; border-radius: 4px; box-shadow: 0 0 8px rgba(0,0,0,0.5); }}
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


def _render_block(preview: ImagePreview) -> str:
    tiles_html = "\n".join(
        f"""<div class="tile-card">
        <img src="{tile.data_url}" alt="{tile.label}" />
        <div class="meta">{tile.label}<br/>coverage {tile.coverage:.2f}<br/>score {tile.score:.2f}</div>
      </div>"""
        for tile in preview.tiles
    )
    return f"""
    <section class="image-block">
      <div class="meta">{preview.path} — {preview.width}×{preview.height}</div>
      <img class="original" src="{preview.original_data_url}" alt="{preview.path}" />
      <div class="tiles">
        {tiles_html}
      </div>
    </section>
    """


def render_preview(previews: list[ImagePreview], output_path: Path) -> Path:
    blocks = "\n".join(_render_block(preview) for preview in previews)
    html = HTML_TEMPLATE.format(blocks=blocks)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a preview HTML for gallery tiles.")
    parser.add_argument("images_dir", type=Path)
    parser.add_argument("--db", type=Path, default=Path("mosaic.duckdb"))
    parser.add_argument("--out", type=Path, default=Path("preview.html"))
    parser.add_argument("--tile-side", type=int, default=64)
    parser.add_argument("--max-tiles", type=int, default=3)
    parser.add_argument("--no-progress", action="store_true", help="Disable progress output")
    args = parser.parse_args()

    previews = ingest_gallery(
        images_dir=args.images_dir,
        db_path=args.db,
        tile_side=args.tile_side,
        max_tiles=args.max_tiles,
        show_progress=not args.no_progress,
    )
    render_preview(previews, args.out)
    print(f"Wrote preview to {args.out}")


if __name__ == "__main__":
    main()

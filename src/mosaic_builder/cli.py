import typer

from mosaic_builder import pipeline

app = typer.Typer(add_completion=False)


@app.command()
def quick(
    ref: str,
    tiles: str,
    out: str,
    tile_side: int = 24,
    grain: float = 1.0,
):
    """
    Build a mosaic.
    grain: 1.0 = coarse (no overlap), 0.5 = finer (overlap), >1.0 = skip (coarser)
    """
    pipeline.quick(ref, tiles, out, tile_side=tile_side, grain=grain)


if __name__ == "__main__":
    app()

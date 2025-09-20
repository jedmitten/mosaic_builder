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
    min_repeat_distance: int = 0,
):
    """
    grain: 1.0 = coarse, 0.5 = finer (overlap), >1.0 = skip
    min_repeat_distance: 0 = allow repeats anywhere; 1 = no adjacent repeats; 2+ increases spacing.
    """
    pipeline.quick(
        ref,
        tiles,
        out,
        tile_side=tile_side,
        grain=grain,
        min_repeat_distance=min_repeat_distance,
    )


if __name__ == "__main__":
    app()

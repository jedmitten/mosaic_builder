import io
from contextlib import redirect_stdout

from mosaic_builder.progress import iter_with_progress


def _collect(items, *, enabled):
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = list(iter_with_progress(items, desc="Working", enabled=enabled))
    return result, buf.getvalue()


def test_passthrough_yields_every_item():
    result, _ = _collect([1, 2, 3], enabled=True)
    assert result == [1, 2, 3]


def test_disabled_prints_nothing():
    result, output = _collect([1, 2, 3], enabled=False)
    assert result == [1, 2, 3]
    assert output == ""


def test_empty_sequence_prints_nothing():
    result, output = _collect([], enabled=True)
    assert result == []
    assert output == ""


def test_enabled_draws_a_bar_reaching_full():
    _, output = _collect(range(4), enabled=True)
    assert "Working: starting (4 items)" in output
    assert "4/4" in output
    assert "#" * 30 in output


def test_accepts_a_generator():
    result, _ = _collect((n * 2 for n in range(3)), enabled=False)
    assert result == [0, 2, 4]

import io
from contextlib import redirect_stderr

import pytest

from mosaic_builder.cli import cli_errors


def _run(exc):
    buf = io.StringIO()
    with redirect_stderr(buf), pytest.raises(SystemExit) as caught:
        with cli_errors():
            raise exc
    return caught.value.code, buf.getvalue()


def test_missing_file_exits_one_with_one_line():
    code, err = _run(FileNotFoundError("no such target: cat.png"))
    assert code == 1
    assert err.strip() == "error: no such target: cat.png"
    assert "Traceback" not in err


def test_value_error_is_reported():
    code, err = _run(ValueError("No tiles in database"))
    assert code == 1
    assert "No tiles in database" in err


def test_schema_version_error_is_reported():
    from mosaic_builder.duckdb_store import SchemaVersionError

    code, err = _run(SchemaVersionError("database is out of date; delete and re-ingest"))
    assert code == 1
    assert "out of date" in err


def test_success_path_is_transparent():
    with cli_errors():
        value = 41 + 1
    assert value == 42


def test_programming_errors_are_not_swallowed():
    with pytest.raises(TypeError):
        with cli_errors():
            raise TypeError("this is a bug, not a user error")

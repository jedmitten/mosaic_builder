"""Shared command-line plumbing: friendly error reporting for module entry points."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

# Errors that represent a user mistake rather than a defect: a missing file, a bad
# argument, an empty or out-of-date database. SchemaVersionError subclasses RuntimeError.
USER_ERRORS = (FileNotFoundError, ValueError, RuntimeError)


@contextmanager
def cli_errors() -> Iterator[None]:
    """Turn expected user errors into a one-line message and exit status 1.

    Programming errors keep their traceback; only the error types a user can
    actually cause are caught.
    """
    try:
        yield
    except USER_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None

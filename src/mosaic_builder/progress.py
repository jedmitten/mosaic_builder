"""Shared text progress-bar helper used by the ingest, match, and render loops."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TypeVar

T = TypeVar("T")

_BAR_WIDTH = 30


def iter_with_progress(items: Iterable[T], desc: str, enabled: bool = True) -> Iterator[T]:
    """Yield from ``items`` while drawing a single-line progress bar on stdout.

    The iterable is materialised so the total is known up front. When ``enabled`` is
    False, or the sequence is empty, this is a plain pass-through with no output.
    """
    sequence = list(items)
    total = len(sequence)
    if not enabled or total == 0:
        yield from sequence
        return

    print(f"{desc}: starting ({total} items)")
    for idx, item in enumerate(sequence, 1):
        filled = int(_BAR_WIDTH * idx / total)
        bar = "#" * filled + "-" * (_BAR_WIDTH - filled)
        print(f"\r{desc}: [{bar}] {idx}/{total}", end="", flush=True)
        yield item
    print()

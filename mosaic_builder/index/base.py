from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Tuple

import numpy as np

Array = np.ndarray


@dataclass(frozen=True)
class SearchResult:
    indices: Array  # shape (k,)
    distances: Array  # shape (k,)


class VectorIndex(ABC):
    """Stable interface for nearest-neighbor search."""

    @abstractmethod
    def build(self, vectors: Array) -> None:
        """Build or load the index from a (N, D) array."""

    @abstractmethod
    def query(self, vec: Array, k: int = 1) -> SearchResult:
        """Return k nearest neighbors to vec (D,)."""

    @abstractmethod
    def save(self, path: str) -> None:
        """Persist index metadata (optional for in-memory backends)."""

    @abstractmethod
    def load(self, path: str) -> None:
        """Load a previously saved index (optional)."""

    def batch_query(self, vecs: Array, k: int = 1) -> Tuple[Array, Array]:
        n = vecs.shape[0]
        idx = np.empty((n, k), dtype=int)
        dist = np.empty((n, k), dtype=float)
        for i, v in enumerate(vecs):
            r = self.query(v, k=k)
            idx[i], dist[i] = r.indices, r.distances
        return idx, dist

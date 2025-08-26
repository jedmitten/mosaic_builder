from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np
import numpy.typing as npt

# Explicit, mypy-friendly aliases
VectorF32: TypeAlias = npt.NDArray[np.float32]  # shape: (D,)
MatrixF32: TypeAlias = npt.NDArray[np.float32]  # shape: (N, D)
IndexArray: TypeAlias = npt.NDArray[np.intp]  # indices vector

Array = np.ndarray


@dataclass(frozen=True)
class SearchResult:
    indices: IndexArray  # (k,)
    distances: VectorF32  # (k,)


class VectorIndex(ABC):
    """Stable interface for nearest-neighbor search."""

    @abstractmethod
    def build(self, vectors: MatrixF32) -> None:
        """Build or load the index from a (N, D) array."""

    @abstractmethod
    def query(self, vec: VectorF32, k: int = 1) -> SearchResult:
        """Return k nearest neighbors to vec (D,)."""

    @abstractmethod
    def save(self, path: str) -> None:
        """Persist index metadata (optional for in-memory backends)."""

    @abstractmethod
    def load(self, path: str) -> None:
        """Load a previously saved index (optional)."""

    def batch_query(self, vecs: MatrixF32, k: int = 1) -> tuple[IndexArray, MatrixF32]:
        """Vectorized helper: query many vectors. Returns (indices, distances)."""
        n = int(vecs.shape[0])
        idx: IndexArray = np.empty((n, k), dtype=np.intp)
        dist: MatrixF32 = np.empty((n, k), dtype=np.float32)
        for i, v in enumerate(vecs):
            v32: VectorF32 = v.astype(np.float32, copy=False)
            r = self.query(v32, k=k)
            idx[i], dist[i] = r.indices, r.distances
        return idx, dist

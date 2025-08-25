import numpy as np

from mosaic_builder.index.base import Array, SearchResult, VectorIndex


class BruteForceIndex(VectorIndex):
    def __init__(self, metric: str = "euclidean"):
        self.metric = metric
        self.vectors: Array | None = None

    def build(self, vectors: Array) -> None:
        self.vectors = np.ascontiguousarray(vectors, dtype=np.float32)

    def _euclidean(self, vec: Array) -> np.ndarray:
        diff = self.vectors - vec[None, :]
        return np.sqrt(np.einsum("ij,ij->i", diff, diff))

    def _cosine(self, vec: Array) -> np.ndarray:
        A = self.vectors
        num = A @ vec
        denom = np.linalg.norm(A, axis=1) * np.linalg.norm(vec) + 1e-9
        return 1.0 - (num / denom)

    def query(self, vec: Array, k: int = 1) -> SearchResult:
        assert self.vectors is not None
        if self.metric == "euclidean":
            dists = self._euclidean(vec)
        elif self.metric == "cosine":
            dists = self._cosine(vec)
        else:
            raise ValueError(f"Unsupported metric: {self.metric}")
        order = np.argpartition(dists, k)[:k]
        order = order[np.argsort(dists[order])]
        return SearchResult(indices=order, distances=dists[order])

    def save(self, path: str) -> None:
        if self.vectors is not None:
            np.save(path, self.vectors)

    def load(self, path: str) -> None:
        self.vectors = np.load(path)

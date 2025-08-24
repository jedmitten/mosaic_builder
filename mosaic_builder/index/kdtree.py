import numpy as np
from sklearn.neighbors import KDTree
from mosaic_builder.index.base import VectorIndex, SearchResult, Array


class KDTreeIndex(VectorIndex):
    def __init__(self, metric: str = "euclidean", leaf_size: int = 40):
        if metric not in ("euclidean", "manhattan"):
            raise ValueError("KDTree supports euclidean or manhattan.")
        self.metric = "euclidean" if metric == "euclidean" else "manhattan"
        self.leaf_size = leaf_size
        self.tree: KDTree | None = None
        self.vectors: Array | None = None

    def build(self, vectors: Array) -> None:
        self.vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        self.tree = KDTree(self.vectors, leaf_size=self.leaf_size, metric=self.metric)

    def query(self, vec: Array, k: int = 1) -> SearchResult:
        assert self.tree is not None
        dist, idx = self.tree.query(vec.reshape(1, -1), k=k)
        return SearchResult(indices=idx[0], distances=dist[0])

    def save(self, path: str) -> None:
        import json, os

        base = os.path.splitext(path)[0]
        np.save(base + ".npy", self.vectors)
        with open(base + ".json", "w") as f:
            json.dump({"metric": self.metric, "leaf_size": self.leaf_size}, f)

    def load(self, path: str) -> None:
        import json, os

        base = os.path.splitext(path)[0]
        self.vectors = np.load(base + ".npy")
        with open(base + ".json") as f:
            meta = json.load(f)
        self.metric = meta["metric"]
        self.leaf_size = meta["leaf_size"]
        self.tree = KDTree(self.vectors, leaf_size=self.leaf_size, metric=self.metric)

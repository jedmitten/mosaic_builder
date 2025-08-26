# mosaic_builder/index/kdtree.py
import numpy as np
from scipy.spatial import cKDTree

from mosaic_builder.index.base import MatrixF32, SearchResult, VectorF32, VectorIndex


class KDTreeIndex(VectorIndex):
    def __init__(self, metric: str = "euclidean", leaf_size: int = 40):
        # cKDTree is Euclidean (L2) only; emulate manhattan via p=1 on KDTree if needed,
        # but for speed stick to Euclidean here.
        if metric != "euclidean":
            raise ValueError("cKDTree backend supports 'euclidean' only.")
        self.metric = "euclidean"
        self.leaf_size = leaf_size  # kept for API symmetry; cKDTree ignores it
        self.tree: cKDTree | None = None
        self.vectors: MatrixF32 | None = None

    def build(self, vectors: MatrixF32) -> None:
        self.vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        self.tree = cKDTree(self.vectors)

    def query(self, vec: VectorF32, k: int = 1) -> SearchResult:
        assert self.tree is not None
        dist, idx = self.tree.query(vec.reshape(1, -1), k=k)
        # cKDTree returns shape (1, k) when k>1, or scalars when k==1
        if k == 1:
            return SearchResult(indices=np.array([int(idx)]), distances=np.array([float(dist)]))
        return SearchResult(indices=idx[0].astype(int), distances=dist[0].astype(float))

    def save(self, path: str) -> None:
        import json
        import os

        base = os.path.splitext(path)[0]
        np.save(base + ".npy", self.vectors)
        with open(base + ".json", "w") as f:
            json.dump({"metric": self.metric, "leaf_size": self.leaf_size}, f)

    def load(self, path: str) -> None:
        import json
        import os

        base = os.path.splitext(path)[0]
        self.vectors = np.load(base + ".npy")
        with open(base + ".json") as f:
            meta = json.load(f)
        self.metric = meta["metric"]
        self.leaf_size = meta["leaf_size"]
        self.tree = cKDTree(self.vectors)

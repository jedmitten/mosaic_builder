import numpy as np
from mosaic_builder.index.base import VectorIndex, SearchResult, Array


class HNSWIndex(VectorIndex):
    def __init__(
        self,
        metric: str = "euclidean",
        M: int = 16,
        ef_construction: int = 200,
        ef_search: int = 64,
    ):
        self.metric = metric
        self.M = M
        self.ef_construction = ef_construction
        self.ef_search = ef_search
        self.index = None
        self.dim = None

    def build(self, vectors: Array) -> None:
        try:
            import hnswlib
        except ImportError as e:
            raise RuntimeError("hnswlib not installed. `pip install hnswlib`.") from e
        space = "l2" if self.metric == "euclidean" else "cosine"
        self.dim = vectors.shape[1]
        self.index = hnswlib.Index(space=space, dim=self.dim)
        self.index.init_index(
            max_elements=vectors.shape[0],
            ef_construction=self.ef_construction,
            M=self.M,
        )
        self.index.add_items(vectors.astype(np.float32))
        self.index.set_ef(self.ef_search)

    def query(self, vec: Array, k: int = 1) -> SearchResult:
        labels, distances = self.index.knn_query(vec.astype(np.float32), k=k)
        return SearchResult(indices=labels[0], distances=distances[0])

    def save(self, path: str) -> None:
        self.index.save_index(path)

    def load(self, path: str) -> None:
        import hnswlib

        # space/dim are encoded in file; hnswlib reconstructs them
        self.index = hnswlib.Index(space="l2", dim=1)
        self.index.load_index(path)

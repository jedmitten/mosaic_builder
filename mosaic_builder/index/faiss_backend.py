import numpy as np
from mosaic_builder.index.base import VectorIndex, SearchResult, Array


class FaissIndex(VectorIndex):
    def __init__(
        self,
        metric: str = "euclidean",
        factory: str = "IVF256,PQ64",
        use_gpu: bool = False,
    ):
        self.metric = metric
        self.factory = factory
        self.use_gpu = use_gpu
        self.index = None
        self.d = None

    def build(self, vectors: Array) -> None:
        try:
            import faiss
        except ImportError as e:
            raise RuntimeError(
                "faiss not installed. `pip install faiss-cpu` or `faiss-gpu`."
            ) from e
        self.d = vectors.shape[1]
        if self.metric != "euclidean":
            raise ValueError("This stub uses L2; extend as needed.")
        self.index = faiss.index_factory(self.d, self.factory, faiss.METRIC_L2)
        if not self.index.is_trained:
            self.index.train(vectors.astype(np.float32))
        self.index.add(vectors.astype(np.float32))

    def query(self, vec: Array, k: int = 1) -> SearchResult:
        D, I = self.index.search(vec.astype(np.float32).reshape(1, -1), k)
        return SearchResult(indices=I[0], distances=D[0])

    def save(self, path: str) -> None:
        import faiss

        faiss.write_index(self.index, path)

    def load(self, path: str) -> None:
        import faiss

        self.index = faiss.read_index(path)

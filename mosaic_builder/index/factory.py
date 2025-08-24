from mosaic_builder.index.base import VectorIndex
from mosaic_builder.index.bruteforce import BruteForceIndex
from mosaic_builder.index.kdtree import KDTreeIndex


def make_index(name: str, **kwargs) -> VectorIndex:
    name = name.lower()
    if name in ("bruteforce", "bf"):
        return BruteForceIndex(**kwargs)
    if name in ("kdtree", "kd"):
        return KDTreeIndex(**kwargs)
    if name == "faiss":
        from mosaic_builder.index.faiss_backend import FaissIndex

        return FaissIndex(**kwargs)
    if name in ("hnsw", "hnswlib"):
        from mosaic_builder.index.hnsw_backend import HNSWIndex

        return HNSWIndex(**kwargs)
    raise ValueError(f"Unknown index backend: {name}")

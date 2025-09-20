import numpy as np
from scipy.spatial import KDTree


class KDIndex:
    def __init__(self, dim: int):
        self._dim = dim
        self._ids: list[str] = []
        self._vecs: list[np.ndarray] = []
        self._tree: KDTree | None = None

    def add(self, id_: str, vec: np.ndarray) -> None:
        assert vec.shape == (self._dim,)
        self._ids.append(id_)
        self._vecs.append(vec.astype(np.float32))

    def build(self) -> None:
        data = np.vstack(self._vecs) if self._vecs else np.zeros((0, self._dim), np.float32)
        self._tree = KDTree(data)

    def query(self, vec: np.ndarray, k: int = 1):
        """Return (dists, ids). dists is shape (1, k_eff). ids is a list[str] length k_eff.
        k_eff = min(k, number_of_items)."""
        assert self._tree is not None
        n = len(self._ids)
        if n == 0:
            # no data: return empty results in the expected shapes
            return np.zeros((1, 0), dtype=np.float32), []

        k_eff = max(1, min(int(k), n))
        dists, idxs = self._tree.query(vec.astype(np.float32), k=k_eff)

        # Normalize shapes to (1, k_eff) and a flat list of ids
        if k_eff == 1:
            dists = np.array([float(dists)], dtype=np.float32).reshape(1, 1)
            idxs = np.array([int(idxs)])
        else:
            dists = np.asarray(dists, dtype=np.float32).reshape(1, k_eff)
            idxs = np.asarray(idxs).reshape(k_eff)

        ids = [self._ids[int(i)] for i in idxs]
        return dists, ids

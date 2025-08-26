import numpy as np

from mosaic_builder.index.factory import make_index


def _toy(n=200, d=8):
    rng = np.random.default_rng(0)
    X = rng.normal(size=(n, d)).astype(np.float32)
    q = X[5] + 0.01
    return X, q


def test_bruteforce_kdtree_api():
    X, q = _toy()
    for backend in ("bruteforce", "kdtree"):
        idx = make_index(backend)
        idx.build(X)
        res = idx.query(q, k=3)
        assert res.indices.shape == (3,)
        assert res.distances.shape == (3,)
        assert np.isfinite(res.distances).all()

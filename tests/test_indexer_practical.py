import numpy as np

from mosaic_builder.indexer import KDIndex


def test_kdindex_add_and_query():
    idx = KDIndex(dim=3)
    rng = np.random.default_rng(1)
    vecs = rng.normal(size=(10, 3)).astype(np.float32)
    ids = [f"id{i}" for i in range(10)]
    for i, v in zip(ids, vecs, strict=False):
        idx.add(i, v)
    idx.build()
    d, i = idx.query(vecs[0], k=1)
    assert i[0] == "id0"
    assert d[0] >= 0.0

from pathlib import Path
import joblib
import numpy as np
from scipy.spatial import cKDTree
from mosaic_builder.stores.factory import open_store
import matplotlib.pyplot as plt


def build_kdtree(store_url: str, index_path: Path, debug_dir: Path | None = None):
    store = open_store(store_url)
    try:
        ids, vecs = store.all_tile_vectors()
    finally:
        store.close()
    tree = cKDTree(vecs)
    joblib.dump(
        {"ids": np.array(ids, dtype=np.int32), "vecs": vecs, "tree": tree}, index_path
    )

    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        plt.figure(figsize=(5, 4))
        plt.scatter(vecs[:, 1], vecs[:, 2], c=vecs[:, 0], cmap="gray", s=3)
        plt.xlabel("a*")
        plt.ylabel("b*")
        plt.title("Tile colors (Lab)")
        plt.savefig(debug_dir / "tile_lab_scatter.png")
        plt.close()

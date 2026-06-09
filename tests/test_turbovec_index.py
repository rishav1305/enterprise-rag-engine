"""P0.2b — TurboVecIndex: build/search/write/load over turbovec.IdMapIndex."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

pytest.importorskip("turbovec")

from rag_engine.retrieval.turbovec_index import TurboVecIndex  # noqa: E402


def _unit(n, dim, seed):
    rng = np.random.default_rng(seed)
    v = rng.standard_normal((n, dim)).astype("float32")
    v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
    return v


def test_build_search_returns_self():
    v = _unit(200, 64, 0)
    ids = [f"chunk:{i}" for i in range(200)]
    idx = TurboVecIndex(dim=64)
    idx.add(ids, v)
    hits = idx.search(v[0], k=5)
    assert len(hits) <= 5
    assert "chunk:0" in [h.chunk_id for h in hits]      # self retrievable
    assert all(isinstance(h.score, float) for h in hits)


def test_write_load_roundtrip(tmp_path):
    v = _unit(200, 64, 1)
    ids = [f"chunk:{i}" for i in range(200)]
    idx = TurboVecIndex(dim=64)
    idx.add(ids, v)
    path = tmp_path / "index.tvim"
    idx.write(str(path))
    assert path.exists()
    # id-map persisted next to the index
    loaded = TurboVecIndex.load(str(path))
    hits = loaded.search(v[3], k=5)
    assert "chunk:3" in [h.chunk_id for h in hits]       # ids survive reload


def test_search_k_bounds():
    v = _unit(50, 32, 2)
    ids = [f"chunk:{i}" for i in range(50)]
    idx = TurboVecIndex(dim=32)
    idx.add(ids, v)
    assert len(idx.search(v[0], k=3)) <= 3
    assert len(idx.search(v[0], k=100)) <= 50            # never more than the corpus


def test_build_index_and_roundtrip_vectors_to_surreal(surreal_local, tmp_path):
    from rag_engine.store.surreal import SurrealStore
    from seeds.targets.turbovec_target import build_index
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db="vec",
                      user="root", password="root")
    st.connect()
    st.apply_schema()
    out = str(tmp_path / "index.tvim")
    n = build_index(st, out_path=out, scale=0.01, dim=128)
    assert n > 0
    # the .tvim + id-map landed, and vectors-by-id are in SurrealDB
    assert (tmp_path / "index.tvim").exists()
    assert (tmp_path / "index.tvim.idmap.json").exists()
    assert st.count_chunks() == n
    # the index reloads and searches
    loaded = TurboVecIndex.load(out)
    assert len(loaded) == n
    st.close()

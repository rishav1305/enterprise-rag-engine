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


# ---- test-hardening (robust directive) ---------------------------------
def test_add_length_mismatch_raises():
    idx = TurboVecIndex(dim=8)
    v = _unit(3, 8, 0)
    with pytest.raises(ValueError):
        idx.add(["chunk:a", "chunk:b"], v)  # 2 ids, 3 vectors


def test_allowlist_with_ids_not_in_index_are_dropped_no_raise():
    v = _unit(20, 8, 5)
    ids = [f"chunk:{i}" for i in range(20)]
    idx = TurboVecIndex(dim=8)
    idx.add(ids, v)
    # allowlist is a superset of the index (includes unknown ids) -> unknowns
    # dropped silently, known ones still searched (no KeyError).
    allow = ["chunk:0", "chunk:2", "chunk:99999", "chunk:does-not-exist"]
    hits = idx.search(v[0], k=5, allowlist_chunk_ids=allow)
    assert {h.chunk_id for h in hits} <= {"chunk:0", "chunk:2"}


def test_allowlist_score_parity_with_unfiltered_restricted():
    # filtered authorized hits == (unfiltered top results restricted to allow)[:k]
    v = _unit(60, 16, 6)
    ids = [f"chunk:{i}" for i in range(60)]
    idx = TurboVecIndex(dim=16)
    idx.add(ids, v)
    allow = [f"chunk:{i}" for i in range(0, 60, 2)]
    filtered = idx.search(v[0], k=5, allowlist_chunk_ids=allow)
    # unfiltered, then restrict to the allowlist, preserving rank order
    unfiltered = idx.search(v[0], k=60)
    restricted = [h for h in unfiltered if h.chunk_id in set(allow)][:5]
    assert [h.chunk_id for h in filtered] == [h.chunk_id for h in restricted]


def test_add_and_search_dim_mismatch_raise():
    idx = TurboVecIndex(dim=16)
    idx.add([f"chunk:{i}" for i in range(5)], _unit(5, 16, 8))
    with pytest.raises(ValueError):
        idx.add(["x", "y"], _unit(2, 8, 9))            # wrong-dim add
    with pytest.raises(ValueError):
        idx.search(_unit(1, 8, 10)[0], k=3)             # wrong-dim query


def test_load_with_dim_override(tmp_path):
    v = _unit(40, 32, 7)
    ids = [f"chunk:{i}" for i in range(40)]
    idx = TurboVecIndex(dim=32)
    idx.add(ids, v)
    out = str(tmp_path / "ovr.tvim")
    idx.write(out)
    # explicit dim override branch on load
    loaded = TurboVecIndex.load(out, dim=32)
    assert loaded.dim == 32
    assert "chunk:0" in [h.chunk_id for h in loaded.search(v[0], k=3)]

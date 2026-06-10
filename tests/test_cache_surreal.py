"""WORKER-D — durable SurrealDB-backed semantic cache (gated on surreal_local).

The durable store must uphold the SAME permission invariant as the in-memory
engine: scope isolation (a low-clearance session never hits a high-clearance entry)
+ re-govern on hit, persisted across the round-trip. The in-memory cache is always
tested; this anchors the durable path on a real SurrealDB. Skips cleanly without
the binary/SDK.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _store(surreal_local):
    from rag_engine.store.surreal import SurrealStore
    st = SurrealStore(dsn=surreal_local["dsn"], ns=surreal_local["ns"],
                      db=surreal_local["db"], user=surreal_local["user"],
                      password=surreal_local["pass"])
    st.connect()
    st.apply_schema()
    return st


def _cache(st, threshold=0.9):
    from rag_engine.cache.surreal_cache import SurrealCacheStore
    from rag_engine.retrieval.embedders import HashingEmbedder
    return SurrealCacheStore(st, embedder=HashingEmbedder(dim=128),
                             similarity_threshold=threshold, ttl_seconds=3600)


def _id(ids, session):
    return list(ids)


def test_durable_put_then_get_roundtrips(surreal_local):
    from rag_engine.schemas import Session
    c = _cache(_store(surreal_local))
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    c.put("what is Q3 revenue", s, chunk_ids=["c1", "c2"], answer="42")
    hit = c.get("what is Q3 revenue", s, _id)
    assert hit is not None and hit.answer == "42" and hit.chunk_ids == ["c1", "c2"]


def test_durable_scope_isolation_no_cross_clearance_leak(surreal_local):
    from rag_engine.schemas import Session
    c = _cache(_store(surreal_local))
    cfo = Session(user_id="cfo", roles=["C_SUITE", "FINANCE"], clearance_level=5)
    intern = Session(user_id="intern", roles=["INTERN"], clearance_level=1)
    c.put("what is exec compensation", cfo, chunk_ids=["comp:1"], answer="SECRET-4.2M")
    # the intern must NOT see the CFO's durable entry for an identical query
    assert c.get("what is exec compensation", intern, _id) is None


def test_durable_regovern_denies_all_is_miss(surreal_local):
    from rag_engine.schemas import Session
    c = _cache(_store(surreal_local))
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    c.put("what is Q3 revenue", s, chunk_ids=["c1"], answer="42")
    deny_all = lambda ids, session: []  # noqa: E731
    assert c.get("what is Q3 revenue", s, deny_all) is None


def test_durable_invalidate_version_clears_stale(surreal_local):
    from rag_engine.schemas import Session
    st = _store(surreal_local)
    c = _cache(st)
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    c.put("what is Q3 revenue", s, chunk_ids=["c1"], answer="42")
    c.invalidate_version("hashing-v1")          # the version we wrote under (CDC seam)
    assert c.get("what is Q3 revenue", s, _id) is None  # invalidated -> miss

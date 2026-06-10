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


def test_durable_partial_denial_is_miss(surreal_local):
    from rag_engine.schemas import Session
    c = _cache(_store(surreal_local))
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    c.put("summarize the memo", s, chunk_ids=["pub:1", "secret:2"], answer="...$4.2M...")
    deny_secret = lambda ids, session: [i for i in ids if i != "secret:2"]  # noqa: E731
    # partial denial -> miss (opaque answer can't be re-masked) — same as in-memory
    assert c.get("summarize the memo", s, deny_secret) is None


def test_durable_govern_fn_raises_is_fail_closed(surreal_local):
    from rag_engine.schemas import Session
    c = _cache(_store(surreal_local))
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    c.put("what is Q3 revenue", s, chunk_ids=["c1"], answer="42")

    def boom(ids, session):
        raise RuntimeError("governance down")

    assert c.get("what is Q3 revenue", s, boom) is None


def test_durable_embedder_version_mismatch_is_miss(surreal_local):
    from rag_engine.cache.surreal_cache import SurrealCacheStore
    from rag_engine.retrieval.embedders import HashingEmbedder
    from rag_engine.schemas import Session
    st = _store(surreal_local)
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    # write under v1
    SurrealCacheStore(st, HashingEmbedder(dim=128), 0.9, 3600,
                      embedder_version="v1").put("q one two", s, chunk_ids=["c1"], answer="42")
    # read under v2 -> the WHERE embedder_version filter excludes the v1 row -> miss
    reader = SurrealCacheStore(st, HashingEmbedder(dim=128), 0.9, 3600,
                               embedder_version="v2")
    assert reader.get("q one two", s, _id) is None

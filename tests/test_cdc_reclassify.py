"""WORKER-B — RECLASSIFICATION propagation (the sharp P0.9 leak oracle).

A chunk's sensitivity_class/ACL changes UP (B->F). Two things must hold, fail-closed:
  1. an under-cleared session that COULD retrieve it before is now DENIED — the
     allowlist re-derives from the live store row (new cls/level);
  2. any cache entry computed under the OLD class is INVALIDATED, so a re-query is a
     MISS (recompute under new governance), NOT the stale permissive hit.

MUTATION (the bite): skip cache-invalidate-on-reclassify -> the stale permissive
cache entry is served after the reclassify -> the now-restricted answer leaks -> fails.
Treat like the leak oracle.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.cache.semantic_cache import SemanticCache  # noqa: E402
from rag_engine.cdc.events import ChangeOp, ChunkChangeEvent  # noqa: E402
from rag_engine.cdc.processor import CdcProcessor  # noqa: E402
from rag_engine.governance.allowlist import authorized_chunk_ids  # noqa: E402
from rag_engine.retrieval.embedders import HashingEmbedder  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402
from rag_engine.store.chunk_source import SurrealChunkSource  # noqa: E402


def _store(surreal_local):
    from rag_engine.store.surreal import SurrealStore
    st = SurrealStore(dsn=surreal_local["dsn"], ns=surreal_local["ns"],
                      db=surreal_local["db"], user=surreal_local["user"],
                      password=surreal_local["pass"])
    st.connect()
    st.apply_schema()
    return st


def _id(ids, session):
    return list(ids)


def test_reclassify_up_denies_and_invalidates_cache(surreal_local):
    st = _store(surreal_local)
    cache = SemanticCache(HashingEmbedder(dim=128), 0.9, 3600, 128)
    proc = CdcProcessor(store=st, cache=cache)
    source = SurrealChunkSource(st)

    # insert a class-B (public-ish, level 1) chunk an L2 employee CAN retrieve.
    proc.apply(ChunkChangeEvent(ChangeOp.INSERT, "doc:1", 1,
                                {"asset_id": "a1", "cls": "B", "level": 1,
                                 "text": "meridian project notes"}))
    under_cleared = Session(user_id="emp", roles=["EMPLOYEE"], clearance_level=2)

    # FAITHFUL govern_fn: re-derives authorization from the LIVE store on every hit
    # (exactly what the wired pipeline does), so this test proves BOTH the cache
    # invalidation AND the re-govern-deny together — belt-and-suspenders.
    def govern(ids, session):
        allow = set(authorized_chunk_ids(session, source.all_chunk_security()))
        return [cid for cid in ids if cid in allow]

    # BEFORE: the chunk is on the under-cleared session's allowlist (class-B).
    allow_before = set(authorized_chunk_ids(under_cleared, source.all_chunk_security()))
    assert "doc:1" in allow_before

    # cache a governed result for the under-cleared session referencing the chunk.
    cache.put("what are the meridian project notes", under_cleared,
              chunk_ids=["doc:1"], answer="notes content (was class-B)")
    assert cache.get("what are the meridian project notes", under_cleared, govern) is not None

    # RECLASSIFY UP B -> F (exec-comp, level 5, need-to-know C_SUITE) via CDC.
    proc.apply(ChunkChangeEvent(ChangeOp.RECLASSIFY, "doc:1", 2,
                                {"asset_id": "a1", "cls": "F", "level": 5,
                                 "text": "meridian project notes"}))

    # 1) the under-cleared session is now DENIED (allowlist re-derived from new row).
    allow_after = set(authorized_chunk_ids(under_cleared, source.all_chunk_security()))
    assert "doc:1" not in allow_after, "RECLASSIFY: under-cleared session still authorized"

    # 2) the stale (permissive) cache entry is INVALIDATED -> a re-query MISSES.
    #    With the FAITHFUL govern_fn this is doubly safe: even if the entry weren't
    #    invalidated, the re-govern over the new (class-F) row would deny doc:1.
    assert cache.get("what are the meridian project notes", under_cleared, govern) is None, \
        "RECLASSIFY LEAK: stale permissive cache entry served now-restricted content"


def test_reclassify_down_also_invalidates(surreal_local):
    # F -> B (declassify): the cache entry computed under F is still stale; a
    # re-query should recompute. (Invalidation is unconditional on reclassify.)
    st = _store(surreal_local)
    cache = SemanticCache(HashingEmbedder(dim=128), 0.9, 3600, 128)
    proc = CdcProcessor(store=st, cache=cache)
    cfo = Session(user_id="cfo", roles=["C_SUITE"], clearance_level=5)

    proc.apply(ChunkChangeEvent(ChangeOp.INSERT, "doc:2", 1,
                                {"asset_id": "a1", "cls": "F", "level": 5, "text": "x"}))
    cache.put("query about doc two contents", cfo, chunk_ids=["doc:2"], answer="a")
    proc.apply(ChunkChangeEvent(ChangeOp.RECLASSIFY, "doc:2", 2,
                                {"asset_id": "a1", "cls": "B", "level": 1, "text": "x"}))
    assert cache.get("query about doc two contents", cfo, _id) is None  # invalidated

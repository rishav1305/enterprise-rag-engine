"""WORKER-A — DELETE propagation: a deleted chunk leaves NO stale authorization.

End-to-end through the live store + the real cache: a CDC delete makes the chunk
UN-retrievable across all modes + dropped from the allowlist source + every cache
entry referencing it is gone.

MUTATION (the bite): skip store.delete_chunk OR skip cache.invalidate_chunk in the
processor -> the deleted chunk is still retrievable / still cache-served -> fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.cache.semantic_cache import SemanticCache  # noqa: E402
from rag_engine.cdc.events import ChangeOp, ChunkChangeEvent  # noqa: E402
from rag_engine.cdc.processor import CdcProcessor  # noqa: E402
from rag_engine.retrieval.embedders import HashingEmbedder  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402


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


def test_delete_propagates_to_store_allowlist_and_cache(surreal_local):
    st = _store(surreal_local)
    cache = SemanticCache(HashingEmbedder(dim=128), 0.9, 3600, 128)
    proc = CdcProcessor(store=st, cache=cache)

    # seed via CDC (insert) — a chunk + a cached result that references it
    proc.apply(ChunkChangeEvent(ChangeOp.INSERT, "drop", 1,
                                {"asset_id": "a1", "cls": "B", "level": 1,
                                 "text": "meridian secret content"}))
    proc.apply(ChunkChangeEvent(ChangeOp.INSERT, "keep", 1,
                                {"asset_id": "a1", "cls": "B", "level": 1,
                                 "text": "meridian public overview"}))
    s = Session(user_id="u", roles=["EMPLOYEE"], clearance_level=2)
    cache.put("what is the meridian secret", s, chunk_ids=["drop"], answer="THE SECRET")
    assert cache.get("what is the meridian secret", s, _id) is not None  # cached

    # DELETE via CDC
    proc.apply(ChunkChangeEvent(ChangeOp.DELETE, "drop", 2))

    # 1) gone from the store / allowlist source
    assert st.get_chunk_row("drop") is None
    ids = {str(r.get("id")) for r in st.chunk_security_rows()}
    assert not any("drop" in i for i in ids)

    # 2) un-retrievable in all modes
    allow = ["drop", "keep"]  # even a stale allowlist naming it
    for result in (st.graph_neighbors("keep", allow),
                   st.structured_rows("a1", allow),
                   st.fulltext_search("meridian", allow)):
        assert not any("drop" in str(r.get("id")) for r in result)

    # 3) the cache entry referencing it is GONE (no stale hit)
    assert cache.get("what is the meridian secret", s, _id) is None, \
        "DELETE LEAK: a stale cache entry still served the deleted chunk's answer"

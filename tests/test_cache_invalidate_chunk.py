"""P0.9 T1 — cache invalidate_chunk: drop every entry referencing a chunk_id.

The reclassify/delete cache propagation: when a chunk is deleted or reclassified,
any cached answer COMPUTED over it is stale and must be dropped — so a re-query
recomputes under the new state instead of serving the stale governed result.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.cache.semantic_cache import SemanticCache  # noqa: E402
from rag_engine.retrieval.embedders import HashingEmbedder  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402


def _cache():
    return SemanticCache(embedder=HashingEmbedder(dim=128),
                         similarity_threshold=0.9, ttl_seconds=3600, max_entries=128)


def _id(ids, session):
    return list(ids)


def _s():
    return Session(user_id="a", roles=["FINANCE"], clearance_level=3)


def test_invalidate_chunk_drops_referencing_entry():
    c = _cache()
    c.put("what is Q3 revenue", _s(), chunk_ids=["c1", "c2"], answer="42")
    assert c.get("what is Q3 revenue", _s(), _id) is not None   # cached
    c.invalidate_chunk("c2")                                    # c2 changed/deleted
    assert c.get("what is Q3 revenue", _s(), _id) is None       # stale entry gone


def test_invalidate_chunk_leaves_unrelated_entries():
    c = _cache()
    c.put("query about revenue figures", _s(), chunk_ids=["c1"], answer="rev")
    c.put("query about vacation policy", _s(), chunk_ids=["c2"], answer="pto")
    c.invalidate_chunk("c1")
    assert c.get("query about revenue figures", _s(), _id) is None   # invalidated
    assert c.get("query about vacation policy", _s(), _id) is not None  # untouched


def test_invalidate_chunk_is_idempotent():
    c = _cache()
    c.put("q one two three", _s(), chunk_ids=["c1"], answer="x")
    c.invalidate_chunk("c1")
    c.invalidate_chunk("c1")   # again -> no error
    c.invalidate_chunk("never_existed")  # unknown id -> no-op
    assert c.get("q one two three", _s(), _id) is None

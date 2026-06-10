"""P0.7 T1 — SemanticCache engine: get/put, scope isolation, re-govern on hit.

Core mechanics (the permission-aware leak test lives in test_cache_permission.py;
this covers the engine contract). A hit is possible only WITHIN the same auth
scope AND above the similarity threshold, and a hit RE-APPLIES the supplied
govern_fn for the requesting session before returning.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.cache.semantic_cache import CachedResult, SemanticCache  # noqa: E402
from rag_engine.retrieval.embedders import HashingEmbedder  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402


def _cache(threshold=0.9):
    return SemanticCache(embedder=HashingEmbedder(dim=256),
                         similarity_threshold=threshold, ttl_seconds=3600,
                         max_entries=128)


def _identity_govern(chunk_ids, session):
    # trivial govern_fn: every stored id stays authorized (identity re-govern)
    return list(chunk_ids)


def test_miss_on_empty_cache():
    c = _cache()
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    assert c.get("what is revenue", s, _identity_govern) is None


def test_put_then_identical_query_hits():
    c = _cache()
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    c.put("what is Q3 revenue", s, chunk_ids=["c1", "c2"], answer="42")
    hit = c.get("what is Q3 revenue", s, _identity_govern)
    assert isinstance(hit, CachedResult)
    assert hit.answer == "42"
    assert hit.chunk_ids == ["c1", "c2"]
    assert hit.similarity >= 0.99   # identical query -> ~1.0 cosine


def test_different_scope_is_a_miss():
    c = _cache()
    hi = Session(user_id="a", roles=["FINANCE"], clearance_level=5)
    lo = Session(user_id="b", roles=["FINANCE"], clearance_level=1)
    c.put("what is Q3 revenue", hi, chunk_ids=["c1"], answer="secret")
    # SAME query text, DIFFERENT scope -> must not see the high-clearance entry
    assert c.get("what is Q3 revenue", lo, _identity_govern) is None


def test_below_threshold_is_a_miss():
    c = _cache(threshold=0.99)
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    c.put("what is Q3 revenue for the cloud division", s, chunk_ids=["c1"], answer="x")
    # a semantically different query in the same scope stays below the high bar
    assert c.get("how many vacation days do employees get", s, _identity_govern) is None


def test_hit_reapplies_govern_fn_dropping_now_unauthorized():
    c = _cache()
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    c.put("what is Q3 revenue", s, chunk_ids=["c1", "c2", "c3"], answer="x")

    # govern_fn that now drops c2 (e.g. policy changed) -> the hit must reflect it
    def drop_c2(chunk_ids, session):
        return [cid for cid in chunk_ids if cid != "c2"]

    hit = c.get("what is Q3 revenue", s, drop_c2)
    assert hit is not None
    assert hit.chunk_ids == ["c1", "c3"]      # re-governed, c2 gone
    assert hit.regoverned is True             # the hit went through re-governance


def test_hit_fully_denied_on_regovern_returns_miss():
    # if re-governance now denies ALL stored chunks, a stale answer must NOT be
    # served — treat it as a miss (fail-closed), not an empty-but-cached answer.
    c = _cache()
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    c.put("what is Q3 revenue", s, chunk_ids=["c1", "c2"], answer="x")
    deny_all = lambda ids, session: []  # noqa: E731
    assert c.get("what is Q3 revenue", s, deny_all) is None

"""WORKER-B — semantic-hit mechanics (cosine threshold over the deterministic embedder).

A hit is a cosine match >= threshold within the same scope. The HashingEmbedder is
deterministic so these similarities are STABLE and pinned (probed values): identical
== 1.0, punctuation-only diff == 1.0, a near-paraphrase ('the' inserted) ~= 0.77,
an unrelated query ~= 0.05. Tests choose thresholds that sit between these so the
hit/miss boundary is exercised, not just the extremes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.cache.semantic_cache import SemanticCache  # noqa: E402
from rag_engine.retrieval.embedders import HashingEmbedder  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402


def _cache(threshold):
    return SemanticCache(embedder=HashingEmbedder(dim=256),
                         similarity_threshold=threshold, ttl_seconds=3600,
                         max_entries=128)


def _s():
    return Session(user_id="a", roles=["FINANCE"], clearance_level=3)


def _id(ids, session):
    return list(ids)


def test_identical_query_hits():
    c = _cache(0.99)
    c.put("what is Q3 revenue", _s(), chunk_ids=["c1"], answer="42")
    hit = c.get("what is Q3 revenue", _s(), _id)
    assert hit is not None and hit.similarity >= 0.999


def test_punctuation_only_difference_still_hits():
    c = _cache(0.99)
    c.put("what is Q3 revenue", _s(), chunk_ids=["c1"], answer="42")
    hit = c.get("what is Q3 revenue?", _s(), _id)   # cosine ~1.0 (tokenizer drops '?')
    assert hit is not None


def test_near_paraphrase_hits_under_moderate_threshold():
    c = _cache(0.6)                                  # 0.6 < 0.77 (the paraphrase sim)
    c.put("what is Q3 revenue", _s(), chunk_ids=["c1"], answer="42")
    hit = c.get("what is the Q3 revenue", _s(), _id)
    assert hit is not None and 0.6 <= hit.similarity < 1.0


def test_near_paraphrase_misses_under_strict_threshold():
    c = _cache(0.9)                                  # 0.9 > 0.77 -> the paraphrase misses
    c.put("what is Q3 revenue", _s(), chunk_ids=["c1"], answer="42")
    assert c.get("what is the Q3 revenue", _s(), _id) is None


def test_unrelated_query_misses():
    c = _cache(0.6)
    c.put("what is Q3 revenue", _s(), chunk_ids=["c1"], answer="42")
    assert c.get("how many vacation days do employees get", _s(), _id) is None  # ~0.05


def test_best_match_wins_among_several():
    c = _cache(0.5)
    c.put("what is Q3 revenue", _s(), chunk_ids=["rev"], answer="revenue-answer")
    c.put("how many vacation days do employees get", _s(), chunk_ids=["pto"], answer="pto-answer")
    hit = c.get("what is the Q3 revenue", _s(), _id)   # closest to the revenue entry
    assert hit is not None and hit.chunk_ids == ["rev"]


def test_determinism_repeated_lookups_stable():
    c = _cache(0.6)
    c.put("what is Q3 revenue", _s(), chunk_ids=["c1"], answer="42")
    sims = {c.get("what is the Q3 revenue", _s(), _id).similarity for _ in range(5)}
    assert len(sims) == 1   # identical similarity every time (deterministic embedder)

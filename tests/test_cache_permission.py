"""WORKER-A — the P0.7 leak oracle: a cached answer NEVER crosses a permission boundary.

This is the headline governance invariant of the semantic cache, and it is
fail-closed. A cache keyed only on query similarity would serve a high-clearance
session's cached answer to a low-clearance session asking a semantically identical
question. Both defenses are asserted here:

  1. SCOPE ISOLATION — the low-clearance session gets a CACHE MISS on the
     high-clearance entry (different AuthScope fingerprint).
  2. RE-GOVERN ON HIT — even under a forced same-scope key, re-governance for the
     requester redacts/denies the stored content; the high-clearance answer is
     never returned verbatim.

MUTATION (the bite, which Friday also runs): drop the scope from the cache key
(make put/get scope-blind) -> the low-clearance query hits the high-clearance entry
-> these tests FAIL (cross-clearance leak surfaces).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.cache.semantic_cache import SemanticCache  # noqa: E402
from rag_engine.retrieval.embedders import HashingEmbedder  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402

SECRET = "Q3 exec compensation is $4.2M"   # high-clearance-only answer


def _cache(threshold=0.9):
    return SemanticCache(embedder=HashingEmbedder(dim=256),
                         similarity_threshold=threshold, ttl_seconds=3600,
                         max_entries=128)


def _identity_govern(chunk_ids, session):
    return list(chunk_ids)


# ---- Defense 1: scope isolation ----------------------------------------
def test_low_clearance_misses_high_clearance_entry_same_query():
    c = _cache()
    cfo = Session(user_id="cfo", roles=["C_SUITE", "FINANCE"], clearance_level=5)
    intern = Session(user_id="intern", roles=["INTERN"], clearance_level=1)

    c.put("what is exec compensation", cfo, chunk_ids=["comp:1"], answer=SECRET)

    # SAME query text. The intern must NOT receive the CFO's cached answer.
    hit = c.get("what is exec compensation", intern, _identity_govern)
    assert hit is None, "CROSS-CLEARANCE LEAK: intern hit the CFO's cache entry"


def test_same_clearance_different_roles_also_isolated():
    c = _cache()
    fin = Session(user_id="f", roles=["FINANCE"], clearance_level=3)
    eng = Session(user_id="e", roles=["ENGINEERING"], clearance_level=3)
    c.put("what is the budget", fin, chunk_ids=["b:1"], answer="FINANCE-only budget")
    # same clearance, disjoint roles -> different scope -> miss
    assert c.get("what is the budget", eng, _identity_govern) is None


def test_high_clearance_still_hits_its_own_entry():
    # sanity: isolation must not break the legitimate same-scope hit
    c = _cache()
    cfo = Session(user_id="cfo", roles=["C_SUITE", "FINANCE"], clearance_level=5)
    c.put("what is exec compensation", cfo, chunk_ids=["comp:1"], answer=SECRET)
    hit = c.get("what is exec compensation", cfo, _identity_govern)
    assert hit is not None and hit.answer == SECRET


# ---- Defense 2: re-govern on hit (even if a key collision occurred) ------
def test_regovern_redacts_when_now_unauthorized():
    """Force a same-scope hit, then have govern_fn deny the stored chunks for the
    requester — the answer's supporting context is gone, so it's a fail-closed miss.
    (Models the belt-and-suspenders: even if scope keys ever collided, re-govern
    stops the leak.)"""
    c = _cache()
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    c.put("what is exec compensation", s, chunk_ids=["comp:1"], answer=SECRET)

    # the requester is in-scope for the KEY, but governance now denies the content
    deny_all = lambda ids, session: []  # noqa: E731
    assert c.get("what is exec compensation", s, deny_all) is None

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

    # govern_fn that now drops c2 (e.g. policy changed). The stored ANSWER was
    # synthesized from the FULL chunk set {c1,c2,c3} and is opaque — we cannot
    # safely re-mask it, so ANY re-govern change (here, dropping c2) is a MISS:
    # the pipeline must regenerate fresh from the authorized subset.
    def drop_c2(chunk_ids, session):
        return [cid for cid in chunk_ids if cid != "c2"]

    assert c.get("what is Q3 revenue", s, drop_c2) is None  # partial denial -> miss


def test_hit_fully_denied_on_regovern_returns_miss():
    # if re-governance now denies ALL stored chunks, a stale answer must NOT be
    # served — treat it as a miss (fail-closed), not an empty-but-cached answer.
    c = _cache()
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    c.put("what is Q3 revenue", s, chunk_ids=["c1", "c2"], answer="x")
    deny_all = lambda ids, session: []  # noqa: E731
    assert c.get("what is Q3 revenue", s, deny_all) is None


def test_govern_fn_raises_is_fail_closed():
    # an indeterminate governance outcome (govern_fn raises) must NOT serve a hit.
    c = _cache()
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    c.put("what is Q3 revenue", s, chunk_ids=["c1"], answer="x")

    def boom(ids, session):
        raise RuntimeError("governance backend down")

    assert c.get("what is Q3 revenue", s, boom) is None  # fail-closed, no serve


def test_cross_scope_higher_cosine_entry_still_a_miss():
    # a DIFFERENT scope holds an entry that is a BETTER cosine match; scope
    # filtering must precede the argmax so it's still a miss (no cross-scope leak).
    c = _cache(threshold=0.5)
    hi = Session(user_id="hi", roles=["C_SUITE"], clearance_level=5)
    lo = Session(user_id="lo", roles=["INTERN"], clearance_level=1)
    # hi populates the EXACT query (cosine 1.0 for that text)
    c.put("what is exec compensation", hi, chunk_ids=["c1"], answer="SECRET")
    # lo populates a weaker (lower-cosine) match in ITS scope
    c.put("how many vacation days", lo, chunk_ids=["c2"], answer="pto")
    # lo asks the exec question: the closest entry overall is hi's (cosine 1.0) but
    # it's out of scope -> must MISS, not return hi's higher-cosine answer.
    assert c.get("what is exec compensation", lo, _identity_govern) is None


def test_hit_emits_attributable_audit_event():
    from rag_engine.governance.audit_sink import InMemoryAuditSink
    audit = InMemoryAuditSink()
    c = SemanticCache(embedder=HashingEmbedder(dim=256), similarity_threshold=0.9,
                      ttl_seconds=3600, max_entries=64, audit_sink=audit)
    s = Session(user_id="analyst-7", roles=["FINANCE"], clearance_level=3)
    SENTINEL = "SENTINEL_PII_ANSWER"
    c.put("what is Q3 revenue", s, chunk_ids=["c1_SENTINEL_PII_CHUNK"], answer=SENTINEL)
    assert c.get("what is Q3 revenue", s, _identity_govern) is not None
    recs = audit.by_kind("cache_hit")
    assert len(recs) == 1
    assert recs[0]["detail"]["user_id"] == "analyst-7"   # attributable to the user
    # no-PII: the audit detail carries neither the answer text nor chunk ids/text;
    # only metric attrs + user_id. Distinctive sentinels avoid hex-digit collisions.
    import json
    blob = json.dumps(recs[0]["detail"])
    assert SENTINEL not in blob
    assert "SENTINEL_PII_CHUNK" not in blob
    assert set(recs[0]["detail"].keys()) == {"user_id", "cache_hit", "similarity",
                                             "scope_fp", "n_chunks"}


def test_miss_emits_no_audit_event():
    from rag_engine.governance.audit_sink import InMemoryAuditSink
    audit = InMemoryAuditSink()
    c = SemanticCache(embedder=HashingEmbedder(dim=256), similarity_threshold=0.99,
                      ttl_seconds=3600, max_entries=64, audit_sink=audit)
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    assert c.get("nothing cached yet", s, _identity_govern) is None
    assert audit.by_kind("cache_hit") == []   # a miss is not a hit event

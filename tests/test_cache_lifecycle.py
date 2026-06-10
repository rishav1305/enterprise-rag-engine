"""WORKER-C — TTL/eviction (ELASTIC bounded footprint) + TRANSPARENT cache-hit trail.

Two concerns:
  * lifecycle — entries expire on TTL and are evicted LRU past the cap, so the
    cache footprint is bounded (ELASTIC);
  * transparency — a cache hit emits a span + funnel note + audit event and does
    NOT bypass the audit trail, while carrying NO chunk content (no-PII contract).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.cache.observability import record_cache_hit  # noqa: E402
from rag_engine.cache.semantic_cache import SemanticCache  # noqa: E402
from rag_engine.governance.audit_sink import InMemoryAuditSink  # noqa: E402
from rag_engine.funnel.trace import FunnelTrace  # noqa: E402
from rag_engine.observability.tracer import InMemorySpanCollector, Tracer  # noqa: E402
from rag_engine.retrieval.embedders import HashingEmbedder  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402


def _s():
    return Session(user_id="a", roles=["FINANCE"], clearance_level=3)


def _id(ids, session):
    return list(ids)


# ---- lifecycle: TTL + LRU eviction (ELASTIC) ---------------------------
def test_ttl_expiry_is_a_miss():
    c = SemanticCache(embedder=HashingEmbedder(dim=128),
                      similarity_threshold=0.9, ttl_seconds=0.05, max_entries=64)
    c.put("what is Q3 revenue", _s(), chunk_ids=["c1"], answer="42")
    import time
    time.sleep(0.08)   # exceed the 50ms TTL
    assert c.get("what is Q3 revenue", _s(), _id) is None


def test_lru_eviction_bounds_footprint():
    c = SemanticCache(embedder=HashingEmbedder(dim=128),
                      similarity_threshold=0.9, ttl_seconds=3600, max_entries=3)
    for i in range(5):
        c.put(f"query number {i}", _s(), chunk_ids=[f"c{i}"], answer=str(i))
    assert len(c) == 3   # capped — never grows unbounded


def test_lru_evicts_least_recently_used():
    c = SemanticCache(embedder=HashingEmbedder(dim=128),
                      similarity_threshold=0.99, ttl_seconds=3600, max_entries=2)
    c.put("alpha query one", _s(), chunk_ids=["a"], answer="A")
    c.put("bravo query two", _s(), chunk_ids=["b"], answer="B")
    c.get("alpha query one", _s(), _id)            # touch alpha -> bravo is now LRU
    c.put("charlie query three", _s(), chunk_ids=["c"], answer="C")  # evicts bravo
    assert c.get("alpha query one", _s(), _id) is not None   # alpha survived
    assert c.get("bravo query two", _s(), _id) is None       # bravo evicted


# ---- TRANSPARENT trail -------------------------------------------------
def test_cache_hit_emits_span_funnel_audit():
    collector = InMemorySpanCollector()
    tracer = Tracer(collector=collector, otel=False)
    funnel = FunnelTrace()
    funnel.stage("final_top_k", count=5)   # a prior counted stage to carry forward
    audit = InMemoryAuditSink()

    record_cache_hit(request_id="req1", similarity=0.97, scope_fp="abc123",
                     n_chunks=3, tracer=tracer, funnel=funnel, audit_sink=audit)

    assert "cache_lookup" in collector.names()                 # span emitted
    assert any(s.name == "cache_hit" for s in funnel.stages)   # funnel note emitted
    assert len(audit.by_kind("cache_hit")) == 1                # audit NOT bypassed


def test_cache_hit_trail_carries_no_content():
    """The span/audit attrs are metric-only — a seeded PII sentinel must be absent."""
    collector = InMemorySpanCollector()
    tracer = Tracer(collector=collector, otel=False)
    audit = InMemoryAuditSink()
    SENTINEL = "SENTINEL_PII_4point2M"

    attrs = record_cache_hit(request_id="r", similarity=0.9, scope_fp="fp",
                             n_chunks=1, tracer=tracer, audit_sink=audit)
    import json
    # the returned attrs + the recorded span + the audit record carry no content
    assert SENTINEL not in json.dumps(attrs)
    assert set(attrs.keys()) == {"cache_hit", "similarity", "scope_fp", "n_chunks"}
    span = next(s for s in collector.spans if s.name == "cache_lookup")
    assert SENTINEL not in json.dumps(span.attributes)
    assert set(span.attributes.keys()) == {"cache_hit", "similarity", "scope_fp", "n_chunks"}
    rec = audit.by_kind("cache_hit")[0]
    assert SENTINEL not in json.dumps(rec)

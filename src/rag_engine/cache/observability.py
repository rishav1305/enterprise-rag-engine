"""TRANSPARENT trail for cache hits (P0.7 WORKER-C).

A cache hit short-circuits retrieval/generation, so it MUST still be observable —
otherwise a hit is an invisible answer with no provenance. ``record_cache_hit``
emits the three TRANSPARENT signals for one hit:

  * a tracing span (``cache_lookup``) carrying hit/similarity/scope_fp — metrics
    only, NEVER chunk text or the answer (no-PII contract, mirrors P0.5);
  * a funnel note (the funnel shows the request was served from cache);
  * an ``AuditSink`` ``cache_hit`` event — a hit does NOT bypass the audit trail.

By construction the only attributes attached are the metric keys below, so a cache
hit can never leak content into a span/audit/Langfuse export.
"""

from __future__ import annotations

from typing import Any

# The CLOSED set of cache-hit observability attributes — metrics only, no content.
_HIT_ATTR_KEYS = ("cache_hit", "similarity", "scope_fp", "n_chunks")


def cache_hit_attributes(similarity: float, scope_fp: str, n_chunks: int) -> dict[str, Any]:
    """Metric-only attributes for a cache-hit span/audit. No chunk text, no answer."""
    return {
        "cache_hit": True,
        "similarity": round(float(similarity), 4),
        "scope_fp": scope_fp,        # the SCOPE fingerprint (opaque hash, not identity)
        "n_chunks": int(n_chunks),
    }


def record_cache_hit(
    *,
    request_id: str,
    similarity: float,
    scope_fp: str,
    n_chunks: int,
    tracer: Any | None = None,
    funnel: Any | None = None,
    audit_sink: Any | None = None,
) -> dict[str, Any]:
    """Emit the span + funnel note + audit event for one cache hit.

    Every signal is optional (inject what the caller has). Returns the metric
    attribute dict (handy for assertions). RESILIENT: the audit sink is a side
    channel — its failure is logged by the sink layer, never re-raised here.
    """
    attrs = cache_hit_attributes(similarity, scope_fp, n_chunks)

    if tracer is not None:
        # span carries ONLY the metric attrs — no content by construction.
        with tracer.span("cache_lookup", request_id, **attrs):
            pass

    if funnel is not None:
        # a note-only stage (count carried forward) so the funnel shows the hit.
        funnel.stage("cache_hit", count=None, note=f"served from cache (sim={attrs['similarity']})")

    if audit_sink is not None:
        audit_sink.record_event("cache_hit", attrs)

    return attrs

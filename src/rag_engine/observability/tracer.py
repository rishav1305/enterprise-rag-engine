"""Tracer — per-request retrieval-path spans + cost/token (P0.5, TRANSPARENT).

A thin tracing facade with a pluggable collector so the HOT PATH never depends on
a network export: tests use ``InMemorySpanCollector`` (no creds); production can
add ``LangfuseExporter`` (creds-gated) as a second collector. Each request carries
a ``request_id`` propagated across spans (route -> retrieve -> rerank -> govern ->
generate); cost/token are span attributes computed locally.

If ``opentelemetry`` is installed, the tracer ALSO emits real OTel spans; if not,
the in-memory collector still works (so the core is testable with zero deps).
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

# P0.11a W1 — the CLOSED set of span-attribute keys safe to export to Langfuse Cloud.
# METRIC keys only — NEVER content (answer/chunk text/captions). The exporter filters
# to this allowlist so a careless span("generate", answer=<raw>) can't leak content.
# Allowlist (not denylist) -> a NEW key a future caller adds is dropped by DEFAULT
# (fail-closed): an attribute leaks to Langfuse only if it is explicitly a metric here.
LANGFUSE_ATTR_ALLOWLIST: frozenset[str] = frozenset({
    "request_id", "cost_usd", "tokens", "mode", "n_admitted", "n_retrieved",
    "n_blocked", "decision_counts", "similarity", "scope_fp", "n_chunks",
    "cache_hit", "iteration", "relevance", "grounded", "action", "duration_s",
    "chunk_id", "op", "source_version", "architecture",
})


def filter_span_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """Drop every attribute not in LANGFUSE_ATTR_ALLOWLIST (fail-closed)."""
    return {k: v for k, v in attributes.items() if k in LANGFUSE_ATTR_ALLOWLIST}


@dataclass(slots=True)
class Span:
    name: str
    request_id: str
    attributes: dict[str, Any] = field(default_factory=dict)
    duration_s: float = 0.0


class SpanCollector(Protocol):
    def collect(self, span: Span) -> None: ...


class InMemorySpanCollector:
    """No-creds collector for tests — records every finished span."""

    def __init__(self) -> None:
        self.spans: list[Span] = []

    def collect(self, span: Span) -> None:
        self.spans.append(span)

    # query helpers
    def by_request(self, request_id: str) -> list[Span]:
        return [s for s in self.spans if s.request_id == request_id]

    def names(self) -> list[str]:
        return [s.name for s in self.spans]

    def total_cost(self, request_id: str | None = None) -> float:
        spans = self.by_request(request_id) if request_id else self.spans
        return sum(float(s.attributes.get("cost_usd", 0.0)) for s in spans)

    def total_tokens(self, request_id: str | None = None) -> int:
        spans = self.by_request(request_id) if request_id else self.spans
        return sum(int(s.attributes.get("tokens", 0)) for s in spans)


class Tracer:
    def __init__(self, collector: SpanCollector | None = None,
                 otel: bool = True) -> None:
        self.collector = collector or InMemorySpanCollector()
        self._otel = _maybe_otel_tracer() if otel else None

    @staticmethod
    def new_request_id() -> str:
        return uuid.uuid4().hex

    @contextmanager
    def span(self, name: str, request_id: str, **attributes: Any):
        start = time.perf_counter()
        sp = Span(name=name, request_id=request_id, attributes=dict(attributes))
        otel_cm = (self._otel.start_as_current_span(name) if self._otel else None)
        if otel_cm is not None:
            otel_span = otel_cm.__enter__()
            otel_span.set_attribute("request_id", request_id)
            # FIX7: allowlist-filter OTel attributes too — the no-content guarantee is
            # exporter-AGNOSTIC (not Langfuse-specific). A non-metric key (e.g. a
            # leaked answer) never reaches the OTel span either.
            for k, v in filter_span_attributes(attributes).items():
                otel_span.set_attribute(k, v)
        try:
            yield sp   # callers can sp.attributes[...] = ... to add cost/token
        finally:
            sp.duration_s = time.perf_counter() - start
            if otel_cm is not None:
                for k, v in filter_span_attributes(sp.attributes).items():
                    otel_span.set_attribute(k, v)
                otel_cm.__exit__(None, None, None)
            self.collector.collect(sp)


def _maybe_otel_tracer():
    try:
        from opentelemetry import trace
        return trace.get_tracer("rag_engine")
    except Exception:
        return None


class LangfuseExporter:  # pragma: no cover - creds-gated live path
    """Maps finished spans to Langfuse traces. Creds-gated; never in the test path."""

    def __init__(self, public_key: str, secret_key: str, host: str | None = None) -> None:
        from langfuse import Langfuse

        self._lf = Langfuse(public_key=public_key, secret_key=secret_key, host=host)

    def collect(self, span: Span) -> None:
        # ALLOWLIST-FILTER before export — a span attribute that isn't a known metric
        # key (e.g. a leaked answer/chunk text) is dropped, so no content reaches
        # Langfuse Cloud regardless of what a caller attached.
        safe = filter_span_attributes({**span.attributes, "duration_s": span.duration_s})
        self._lf.trace(name=span.name, id=span.request_id, metadata=safe)

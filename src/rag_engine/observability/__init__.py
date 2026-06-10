"""Observability (P0.5, TRANSPARENT) — per-request tracing, cost/token, spans."""

from .tracer import InMemorySpanCollector, Span, Tracer

__all__ = ["Tracer", "Span", "InMemorySpanCollector"]

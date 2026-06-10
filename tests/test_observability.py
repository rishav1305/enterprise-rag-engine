"""P0.5 WORKER-B — Tracer + InMemorySpanCollector + per-request spans/cost/token."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.observability.tracer import InMemorySpanCollector, Tracer  # noqa: E402


def test_span_records_name_request_and_attrs():
    col = InMemorySpanCollector()
    t = Tracer(col, otel=False)
    rid = Tracer.new_request_id()
    with t.span("retrieve", request_id=rid, mode="vector") as sp:
        sp.attributes["tokens"] = 128
    assert col.names() == ["retrieve"]
    s = col.by_request(rid)[0]
    assert s.attributes["mode"] == "vector" and s.attributes["tokens"] == 128
    assert s.duration_s >= 0.0


def test_request_id_propagates_across_retrieval_path():
    col = InMemorySpanCollector()
    t = Tracer(col, otel=False)
    rid = Tracer.new_request_id()
    for stage in ("route", "retrieve", "rerank", "govern", "generate"):
        with t.span(stage, request_id=rid):
            pass
    spans = col.by_request(rid)
    assert {s.name for s in spans} == {"route", "retrieve", "rerank", "govern", "generate"}
    assert all(s.request_id == rid for s in spans)


def test_cost_and_token_aggregation_per_request():
    col = InMemorySpanCollector()
    t = Tracer(col, otel=False)
    rid = Tracer.new_request_id()
    with t.span("generate", request_id=rid, cost_usd=0.0021, tokens=350):
        pass
    with t.span("rerank", request_id=rid, cost_usd=0.0004, tokens=0):
        pass
    assert abs(col.total_cost(rid) - 0.0025) < 1e-9
    assert col.total_tokens(rid) == 350


def test_two_requests_isolated():
    col = InMemorySpanCollector()
    t = Tracer(col, otel=False)
    r1, r2 = Tracer.new_request_id(), Tracer.new_request_id()
    with t.span("generate", request_id=r1, tokens=10):
        pass
    with t.span("generate", request_id=r2, tokens=20):
        pass
    assert col.total_tokens(r1) == 10
    assert col.total_tokens(r2) == 20


def test_otel_enabled_does_not_break_when_sdk_present_or_absent():
    # Tracer(otel=True) must work whether or not opentelemetry is installed.
    col = InMemorySpanCollector()
    t = Tracer(col, otel=True)
    rid = Tracer.new_request_id()
    with t.span("retrieve", request_id=rid):
        pass
    assert col.by_request(rid)   # the in-memory collector still records

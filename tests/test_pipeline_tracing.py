"""P0.11a W1 — RAGPipeline emits metric-only spans; no content in the trace.

The pipeline wraps route/retrieve/govern/generate in spans. Those spans carry
metric attributes only — a seeded PII sentinel in a chunk must never appear in any
collected span attribute (and the Langfuse exporter further allowlist-filters).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.observability.tracer import InMemorySpanCollector, Tracer  # noqa: E402
from rag_engine.pipeline import RAGPipeline  # noqa: E402
from rag_engine.schemas import Document, SecurityContext, Session  # noqa: E402

SENTINEL = "SENTINEL_PII_PIPELINE_4POINT2M"


def _pipeline_with_collector():
    collector = InMemorySpanCollector()
    pipe = RAGPipeline(tracer=Tracer(collector=collector, otel=False))
    doc = Document(doc_id="d1", title="Notes",
                   content=f"Quarterly notes mention {SENTINEL} in the figures.",
                   security=SecurityContext(allowed_roles=["PUBLIC"], clearance_level=0,
                                            sensitivity_class="A", need_to_know_roles=[]))
    pipe.index_documents([doc])
    return pipe, collector


def test_pipeline_emits_spans():
    pipe, collector = _pipeline_with_collector()
    pipe.query("what are the quarterly notes", Session(user_id="u", roles=["EMPLOYEE"],
                                                       clearance_level=2))
    names = set(collector.names())
    assert {"retrieve", "govern", "generate"} <= names


def test_no_content_in_any_span_attribute():
    pipe, collector = _pipeline_with_collector()
    pipe.query("what are the quarterly notes", Session(user_id="u", roles=["EMPLOYEE"],
                                                       clearance_level=2))
    for sp in collector.spans:
        assert SENTINEL not in json.dumps(sp.attributes), \
            f"content leaked into span {sp.name!r} attributes"

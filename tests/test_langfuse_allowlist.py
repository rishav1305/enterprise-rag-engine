"""P0.11a W1 — Langfuse span-attribute ALLOWLIST: no content can leak to Langfuse.

A span attribute that isn't a known METRIC key is dropped before export, so a
careless ``span("generate", answer=<raw text>)`` can never ship chunk content to
Langfuse Cloud. The exporter filters; callers can't opt content in.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.observability.tracer import (  # noqa: E402
    LANGFUSE_ATTR_ALLOWLIST,
    filter_span_attributes,
)


def test_allowlist_keeps_only_metric_keys():
    attrs = {
        "request_id": "r1", "cost_usd": 0.01, "tokens": 42, "mode": "vector",
        "n_admitted": 3, "decision_counts": {"allow": 2, "deny": 1},
        # the dangerous ones — must be DROPPED:
        "answer": "Bob's salary is $4.2M SECRET",
        "content": "raw chunk text SECRET",
        "chunk_text": "more SECRET",
    }
    out = filter_span_attributes(attrs)
    assert "answer" not in out and "content" not in out and "chunk_text" not in out
    assert out["request_id"] == "r1" and out["tokens"] == 42
    assert set(out) <= LANGFUSE_ATTR_ALLOWLIST


def test_unknown_key_dropped_by_default_fail_closed():
    # a NEW attribute key a future caller adds is dropped unless explicitly allowed.
    out = filter_span_attributes({"some_new_field": "could be content", "tokens": 1})
    assert "some_new_field" not in out
    assert out == {"tokens": 1}


def test_no_secret_substring_survives():
    import json
    attrs = {"answer": "SENTINEL_PII_SECRET", "request_id": "r", "cost_usd": 0.0}
    out = filter_span_attributes(attrs)
    assert "SENTINEL_PII_SECRET" not in json.dumps(out)

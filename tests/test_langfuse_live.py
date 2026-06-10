"""P0.5 — live Langfuse export (creds-gated, NOT part of the CI gate).

Marked ``langfuse`` + skipif no LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY. Proves the
LangfuseExporter maps a span to a Langfuse trace. CI runs
`-m "... and not langfuse"`. No secrets committed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

_HAVE = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


@pytest.mark.langfuse
@pytest.mark.skipif(not _HAVE, reason="no Langfuse keys (set LANGFUSE_PUBLIC_KEY/SECRET_KEY)")
def test_langfuse_exporter_collects_span():
    pytest.importorskip("langfuse")
    from rag_engine.observability.tracer import LangfuseExporter, Tracer

    exporter = LangfuseExporter(public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
                                secret_key=os.environ["LANGFUSE_SECRET_KEY"],
                                host=os.getenv("LANGFUSE_HOST"))
    t = Tracer(exporter, otel=False)
    rid = Tracer.new_request_id()
    with t.span("generate", request_id=rid, cost_usd=0.001, tokens=200):
        pass
    # no exception == the span was exported to Langfuse

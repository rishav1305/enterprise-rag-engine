"""G1 — the un-fakeable parity invariant: the trace IS the engine.

For a persona × class sample, every ``trace.governance[i].decision`` MUST equal
``access.evaluate(chunk, session).decision`` over the SAME retrieved candidates — the
trace cannot claim a governance outcome the engine wouldn't produce. This is the whole
credibility of the glass-box: a re-narration could lie; a trace built from the real
``access.evaluate`` cannot.

MUTATION: hand-set a decision in the assembler (diverge from access.evaluate) → this
test fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rag_engine.config import EngineConfig  # noqa: E402
from rag_engine.governance import access  # noqa: E402
from rag_engine.pipeline import RAGPipeline  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402
from rag_engine.trace import build_trace  # noqa: E402

_CORPUS = Path(__file__).resolve().parents[1] / "corpus"

# a spread spanning allow / mask / partial / deny across the enriched corpus.
_PERSONAS = [
    ("intern", ["INTERN", "EMPLOYEE"], 1),
    ("analyst", ["DATA_ANALYST", "EMPLOYEE"], 2),
    ("sales", ["SALES_MANAGER", "EMPLOYEE"], 3),
    ("director", ["DIRECTOR"], 4),
    ("oncall", ["ON_CALL"], 2),
    ("engineer", ["ENGINEERING"], 3),
    ("cfo", ["C_SUITE", "FINANCE"], 5),
]

_QUERIES = [
    "what is the executive compensation schedule",
    "customer account record dana",
    "engineering on-call incident payments latency",
    "remote work policy",
]


def _pipe():
    p = RAGPipeline(config=EngineConfig())
    p.index_corpus(_CORPUS)
    return p


@pytest.mark.parametrize("pkey,roles,clr", _PERSONAS)
def test_trace_governance_matches_access_evaluate(pkey, roles, clr):
    session = Session(user_id=pkey, roles=roles, clearance_level=clr)
    # use a shared pipeline to get the SAME retrieved candidates the trace will see.
    pipe = _pipe()
    for q in _QUERIES:
        candidates = pipe._retrieve_for_session(q, session)
        ground_truth = [access.evaluate(c.chunk, session).decision for c in candidates]
        trace = build_trace(q, session)
        trace_decisions = [g.decision for g in trace.governance]
        # the trace's per-candidate decisions match access.evaluate exactly (same order)
        assert trace_decisions == ground_truth, (
            f"{pkey} × {q!r}: trace {trace_decisions} != access.evaluate {ground_truth}")


def test_trace_covers_all_four_decisions_live():
    # across the spread, the trace surfaces allow AND mask AND partial AND deny — proof
    # the enriched corpus (G0) makes all four governance outcomes reachable.
    seen = set()
    for pkey, roles, clr in _PERSONAS:
        session = Session(user_id=pkey, roles=roles, clearance_level=clr)
        for q in _QUERIES:
            for g in build_trace(q, session).governance:
                seen.add(g.decision)
    assert {"allow", "mask", "partial", "deny"} <= seen, f"missing decisions: {seen}"


def test_trace_result_is_redacted_not_operator_detail():
    # the persona's result view carries answer + citations + n_withheld — NOT the
    # governance[] ACL detail (that's the auditor lens, separate). An under-cleared
    # persona's result.answer never contains restricted content.
    intern = Session(user_id="i", roles=["INTERN", "EMPLOYEE"], clearance_level=1)
    trace = build_trace("what is the executive compensation schedule", intern)
    assert "$480,000" not in trace.result.answer
    assert "dana.okafor@example.com" not in trace.result.answer
    assert trace.result.n_withheld >= 1

"""WORKER-C — bounded loop + RESILIENT degrade + TRANSPARENT trail.

The loop must be RESILIENT: bounded iterations (no infinite loop even if the grader
always says "insufficient"), and a grader circuit breaker (grader raising -> graceful
degrade, returns/abstains, never hangs or crashes the request). Every iteration emits
a tracing span + funnel note (TRANSPARENT), and the result records WHY it stopped.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.funnel.trace import FunnelTrace  # noqa: E402
from rag_engine.observability.tracer import InMemorySpanCollector, Tracer  # noqa: E402
from rag_engine.selfrag.grader import FakeGrader, GroundednessGrade, RelevanceGrade  # noqa: E402
from rag_engine.selfrag.loop import CorrectiveLoop  # noqa: E402
from rag_engine.schemas import EnrichedChunk, ScoredChunk, SecurityContext, Session  # noqa: E402


def _sc(text):
    chunk = EnrichedChunk(
        chunk_id=text[:8], parent_doc_id="d", parent_title="t", content=text,
        security=SecurityContext(allowed_roles=[], clearance_level=0,
                                 sensitivity_class="A", need_to_know_roles=[]),
    )
    return ScoredChunk(chunk=chunk, score=1.0)


class _Echo:
    def generate(self, query, admitted):
        return " ".join(c.chunk.content for c in admitted)[:200]


def _s():
    return Session(user_id="u", roles=["EMPLOYEE"], clearance_level=2)


# ---- bounded (RESILIENT) -----------------------------------------------
def test_loop_is_bounded_even_when_grader_always_insufficient():
    # a grader that NEVER passes would loop forever without the cap.
    n = {"calls": 0}

    def retrieve_fn(q, s):
        n["calls"] += 1
        return [_sc("always off topic")]

    loop = CorrectiveLoop(
        retrieve_fn=retrieve_fn,
        generator=_Echo(),
        grader=FakeGrader(relevance_threshold=1.01, groundedness_threshold=1.01),  # impossible
        max_iterations=3,
        reformulate_fn=lambda q, i: q,
    )
    res = loop.run("q", _s())
    assert res.iterations == 3            # exactly the cap, not more
    assert n["calls"] == 3                # bounded retrieval
    assert res.abstained is True


# ---- grader circuit breaker (RESILIENT) --------------------------------
class _RaisingGrader:
    def grade_relevance(self, query, chunks):
        raise RuntimeError("grader backend down")

    def grade_groundedness(self, query, answer, chunks):
        raise RuntimeError("grader backend down")


def test_grader_raise_degrades_gracefully_not_hang():
    loop = CorrectiveLoop(
        retrieve_fn=lambda q, s: [_sc("some context")],
        generator=_Echo(),
        grader=_RaisingGrader(),
        max_iterations=3,
    )
    res = loop.run("q", _s())             # must RETURN (not hang/raise)
    assert res.abstained is True
    assert res.stop_reason == "grader_degraded"
    assert res.answer in ("", None)       # nothing served on an indeterminate grade


class _GroundednessRaises:
    """Relevance OK, but groundedness grading raises -> degrade at that point."""
    def grade_relevance(self, query, chunks):
        return RelevanceGrade(True, 1.0, "ok")

    def grade_groundedness(self, query, answer, chunks):
        raise RuntimeError("groundedness backend down")


def test_groundedness_grader_raise_degrades():
    loop = CorrectiveLoop(
        retrieve_fn=lambda q, s: [_sc("relevant context here")],
        generator=_Echo(),
        grader=_GroundednessRaises(),
        max_iterations=2,
    )
    res = loop.run("q", _s())
    assert res.abstained is True and res.stop_reason == "grader_degraded"


# ---- TRANSPARENT trail -------------------------------------------------
def test_each_iteration_emits_span_and_funnel_note():
    collector = InMemorySpanCollector()
    tracer = Tracer(collector=collector, otel=False)
    funnel = FunnelTrace()
    funnel.stage("final_top_k", count=5)   # a prior counted stage to carry forward
    loop = CorrectiveLoop(
        retrieve_fn=lambda q, s: [_sc("off topic")],
        generator=_Echo(),
        grader=FakeGrader(relevance_threshold=1.01, groundedness_threshold=1.01),
        max_iterations=2,
        reformulate_fn=lambda q, i: q,
        tracer=tracer, funnel=funnel, request_id="req-1",
    )
    res = loop.run("q", _s())
    spans = [name for name in collector.names() if name == "selfrag_iteration"]
    assert len(spans) == res.iterations            # one span per iteration
    notes = [s for s in funnel.stages if s.name.startswith("selfrag_iter_")]
    assert len(notes) == res.iterations            # one funnel note per iteration


def test_stop_reason_is_on_provenance():
    loop = CorrectiveLoop(
        retrieve_fn=lambda q, s: [_sc("Q3 revenue 4.2 million dollars")],
        generator=_Echo(),
        grader=FakeGrader(relevance_threshold=0.2, groundedness_threshold=0.4),
        max_iterations=2,
    )
    res = loop.run("what is Q3 revenue", _s())
    assert res.stop_reason == "grounded"   # the honest reason it stopped

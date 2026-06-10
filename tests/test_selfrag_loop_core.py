"""P0.8 T2 — CorrectiveLoop core orchestration (the spine behavior).

retrieve -> grade_relevance -> (reformulate+re-retrieve | proceed) -> generate ->
grade_groundedness -> (refine | abstain | return). Bounded by max_iterations. The
governance-preservation property is tested in test_selfrag_governance.py (WORKER-A);
this covers the happy path + corrective branch + abstain mechanics.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.selfrag.grader import FakeGrader  # noqa: E402
from rag_engine.selfrag.loop import CorrectiveLoop, LoopResult  # noqa: E402
from rag_engine.schemas import EnrichedChunk, ScoredChunk, SecurityContext, Session  # noqa: E402


def _sc(text):
    chunk = EnrichedChunk(
        chunk_id=text[:8], parent_doc_id="d", parent_title="t", content=text,
        security=SecurityContext(allowed_roles=[], clearance_level=0,
                                 sensitivity_class="A", need_to_know_roles=[]),
    )
    return ScoredChunk(chunk=chunk, score=1.0)


class _FixedGen:
    """Generator stub: echoes the context so groundedness is high by construction."""
    def __init__(self, answer=None):
        self._answer = answer

    def generate(self, query, admitted):
        if self._answer is not None:
            return self._answer
        return " ".join(c.chunk.content for c in admitted)[:200]


def _session():
    return Session(user_id="u", roles=["EMPLOYEE"], clearance_level=2)


def test_happy_path_first_retrieval_sufficient_and_grounded():
    good = [_sc("Q3 revenue was 4.2 million dollars for the cloud division")]
    loop = CorrectiveLoop(
        retrieve_fn=lambda q, s: good,
        generator=_FixedGen(),         # echoes context -> grounded
        grader=FakeGrader(relevance_threshold=0.3, groundedness_threshold=0.5),
        max_iterations=3,
    )
    res = loop.run("what is Q3 revenue", _session())
    assert isinstance(res, LoopResult)
    assert res.abstained is False
    assert res.answer
    assert res.iterations == 1                # no correction needed
    assert res.stop_reason == "grounded"


def test_corrective_reretrieve_when_first_insufficient():
    # first retrieval is off-topic; a reformulation yields the relevant chunk
    calls = {"n": 0}

    def retrieve_fn(query, session):
        calls["n"] += 1
        if calls["n"] == 1:
            return [_sc("the cafeteria menu features pasta on Tuesdays")]
        return [_sc("Q3 revenue was 4.2 million dollars")]

    loop = CorrectiveLoop(
        retrieve_fn=retrieve_fn,
        generator=_FixedGen(),
        grader=FakeGrader(relevance_threshold=0.3, groundedness_threshold=0.5),
        max_iterations=3,
        reformulate_fn=lambda q, i: f"{q} revenue dollars",   # adds signal
    )
    res = loop.run("what is Q3 revenue", _session())
    assert res.abstained is False
    assert calls["n"] >= 2                     # it re-retrieved
    assert res.iterations >= 2


def test_abstains_when_retrieval_never_sufficient():
    # retrieval is always off-topic -> after the budget, abstain (don't fabricate)
    loop = CorrectiveLoop(
        retrieve_fn=lambda q, s: [_sc("unrelated cafeteria menu content")],
        generator=_FixedGen(answer="a fabricated confident answer"),
        grader=FakeGrader(relevance_threshold=0.9, groundedness_threshold=0.9),
        max_iterations=2,
        reformulate_fn=lambda q, i: q,         # reformulation doesn't help
    )
    res = loop.run("what is Q3 revenue", _session())
    assert res.abstained is True
    assert res.stop_reason in ("budget_exhausted", "insufficient_retrieval")
    assert res.answer == "" or res.answer is None  # no fabricated answer served


def test_abstains_when_answer_ungrounded():
    # retrieval is relevant, but the generator hallucinates -> groundedness fails ->
    # after the budget, abstain rather than serve the ungrounded answer.
    good = [_sc("Q3 revenue figures for the cloud division this quarter")]
    loop = CorrectiveLoop(
        retrieve_fn=lambda q, s: good,
        generator=_FixedGen(answer="The CEO resigned amid an undisclosed scandal"),
        grader=FakeGrader(relevance_threshold=0.2, groundedness_threshold=0.8),
        max_iterations=2,
    )
    res = loop.run("what is Q3 revenue", _session())
    assert res.abstained is True
    assert res.stop_reason in ("budget_exhausted", "ungrounded")


def test_iterations_never_exceed_cap():
    loop = CorrectiveLoop(
        retrieve_fn=lambda q, s: [_sc("always irrelevant")],
        generator=_FixedGen(),
        grader=FakeGrader(relevance_threshold=0.99, groundedness_threshold=0.99),
        max_iterations=4,
        reformulate_fn=lambda q, i: q,
    )
    res = loop.run("what is Q3 revenue", _session())
    assert res.iterations <= 4                 # bounded — never spins

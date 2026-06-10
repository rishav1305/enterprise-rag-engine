"""WORKER-B — corrective grading mechanics: grades drive the loop's actions.

Relevance grade -> corrective action (insufficient => re-retrieve; sufficient =>
generate). Groundedness grade -> refine/abstain (ungrounded => don't serve).
Abstain-not-fabricate when retrieval/grounding never clears the bar.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.selfrag.grader import FakeGrader  # noqa: E402
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


class _Hallucinate:
    def generate(self, query, admitted):
        return "an entirely fabricated statement about unrelated topics zzz"


def _s():
    return Session(user_id="u", roles=["EMPLOYEE"], clearance_level=2)


def test_sufficient_relevance_proceeds_to_generate():
    relevant = [_sc("Q3 revenue was 4.2 million for the cloud unit")]
    actions = []
    loop = CorrectiveLoop(
        retrieve_fn=lambda q, s: relevant,
        generator=_Echo(),
        grader=FakeGrader(relevance_threshold=0.3, groundedness_threshold=0.4),
        max_iterations=3,
    )
    res = loop.run("what is Q3 revenue", _s())
    actions = [st.action for st in res.steps]
    assert "return" in actions          # proceeded to generate + returned
    assert res.iterations == 1          # no corrective re-retrieve needed


def test_insufficient_relevance_triggers_reretrieve():
    irrelevant = [_sc("the office plants need watering on weekends")]
    loop = CorrectiveLoop(
        retrieve_fn=lambda q, s: irrelevant,
        generator=_Echo(),
        grader=FakeGrader(relevance_threshold=0.5, groundedness_threshold=0.4),
        max_iterations=2,
        reformulate_fn=lambda q, i: q,
    )
    res = loop.run("what is Q3 revenue", _s())
    assert all(st.action in ("reretrieve",) for st in res.steps)  # only ever re-retrieved
    assert res.abstained is True        # never got relevant context


def test_ungrounded_answer_is_not_served():
    relevant = [_sc("Q3 revenue figures for the cloud division this period")]
    loop = CorrectiveLoop(
        retrieve_fn=lambda q, s: relevant,
        generator=_Hallucinate(),       # answer unsupported by context
        grader=FakeGrader(relevance_threshold=0.2, groundedness_threshold=0.7),
        max_iterations=2,
    )
    res = loop.run("what is Q3 revenue", _s())
    assert res.abstained is True
    assert res.answer in ("", None)     # the hallucinated answer is withheld


def test_abstain_does_not_fabricate():
    loop = CorrectiveLoop(
        retrieve_fn=lambda q, s: [_sc("unrelated content about parking permits")],
        generator=_Hallucinate(),
        grader=FakeGrader(relevance_threshold=0.9, groundedness_threshold=0.9),
        max_iterations=2,
        reformulate_fn=lambda q, i: q,
    )
    res = loop.run("what is Q3 revenue", _s())
    assert res.abstained is True
    assert not res.answer               # honest abstention, no fabricated text


def test_groundedness_grade_recorded_in_provenance():
    relevant = [_sc("Q3 revenue was 4.2 million dollars")]
    loop = CorrectiveLoop(
        retrieve_fn=lambda q, s: relevant,
        generator=_Echo(),
        grader=FakeGrader(relevance_threshold=0.2, groundedness_threshold=0.4),
        max_iterations=2,
    )
    res = loop.run("what is Q3 revenue", _s())
    # the step that generated carries a groundedness score (TRANSPARENT provenance)
    graded = [st for st in res.steps if st.groundedness_score is not None]
    assert graded and graded[-1].grounded is True

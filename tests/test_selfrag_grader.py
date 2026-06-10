"""P0.8 T0 — grader contracts + FakeGrader (deterministic, no creds).

The grader is the self-RAG judgment seam: relevance (is the retrieved context good
enough to answer?) pre-generation, and groundedness (is the answer supported by the
context, or hallucinated?) post-generation. FakeGrader is rule-driven so tests are
deterministic with no LLM.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.selfrag.grader import (  # noqa: E402
    FakeGrader,
    Grader,
    GroundednessGrade,
    RelevanceGrade,
)
from rag_engine.schemas import EnrichedChunk, ScoredChunk, SecurityContext  # noqa: E402


def _sc(text, score=1.0):
    chunk = EnrichedChunk(
        chunk_id="c", parent_doc_id="d", parent_title="t", content=text,
        security=SecurityContext(allowed_roles=[], clearance_level=0,
                                 sensitivity_class="A", need_to_know_roles=[]),
    )
    return ScoredChunk(chunk=chunk, score=score)


def test_fakegrader_satisfies_protocol():
    assert isinstance(FakeGrader(), Grader)


def test_relevance_sufficient_on_keyword_overlap():
    g = FakeGrader(relevance_threshold=0.3)
    chunks = [_sc("Q3 revenue was 4.2 million for the cloud division")]
    grade = g.grade_relevance("what is Q3 revenue", chunks)
    assert isinstance(grade, RelevanceGrade)
    assert grade.sufficient is True
    assert 0.0 <= grade.score <= 1.0


def test_relevance_insufficient_when_unrelated():
    g = FakeGrader(relevance_threshold=0.3)
    chunks = [_sc("the cafeteria menu features pasta on Tuesdays")]
    grade = g.grade_relevance("what is Q3 revenue", chunks)
    assert grade.sufficient is False


def test_relevance_insufficient_on_empty_retrieval():
    g = FakeGrader()
    grade = g.grade_relevance("what is Q3 revenue", [])
    assert grade.sufficient is False   # nothing retrieved -> not sufficient


def test_groundedness_grounded_when_answer_supported():
    g = FakeGrader(groundedness_threshold=0.6)
    chunks = [_sc("Q3 revenue was 4.2 million dollars")]
    grade = g.grade_groundedness("what is Q3 revenue", "Q3 revenue was 4.2 million", chunks)
    assert isinstance(grade, GroundednessGrade)
    assert grade.grounded is True


def test_groundedness_ungrounded_on_hallucination():
    g = FakeGrader(groundedness_threshold=0.6)
    chunks = [_sc("Q3 revenue was 4.2 million dollars")]
    # answer asserts a figure absent from context -> hallucination
    grade = g.grade_groundedness("what is Q3 revenue",
                                 "The CEO secretly resigned in Q3 amid scandal", chunks)
    assert grade.grounded is False
    assert grade.score < 0.6


def test_groundedness_ungrounded_on_empty_context():
    g = FakeGrader()
    grade = g.grade_groundedness("q", "a confident fabricated answer", [])
    assert grade.grounded is False   # no context can support any answer

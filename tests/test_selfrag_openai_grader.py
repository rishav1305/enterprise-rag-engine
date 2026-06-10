"""WORKER-D — OpenAICompatGrader: prompt/parse unit-tested (stub), live path gated.

The prompt-building + defensive JSON parsing are testable with a STUBBED _complete
(no network, no creds). The actual network call is creds-gated (@pytest.mark.llm).
The parse is fail-closed: a malformed/empty LLM response grades NOT sufficient /
NOT grounded — you never pass on an unparseable grade.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rag_engine.selfrag.openai_grader import OpenAICompatGrader  # noqa: E402
from rag_engine.schemas import EnrichedChunk, ScoredChunk, SecurityContext  # noqa: E402


def _sc(text):
    chunk = EnrichedChunk(
        chunk_id="c1", parent_doc_id="d", parent_title="t", content=text,
        security=SecurityContext(allowed_roles=[], clearance_level=0,
                                 sensitivity_class="A", need_to_know_roles=[]),
    )
    return ScoredChunk(chunk=chunk, score=1.0)


def _grader(reply):
    g = OpenAICompatGrader(base_url="http://x", model="m", api_key="k")
    g._complete = lambda system, user: reply   # stub the network call
    return g


def test_relevance_parses_clean_json():
    g = _grader('{"sufficient": true, "score": 0.8, "reason": "covers it"}')
    grade = g.grade_relevance("q", [_sc("ctx")])
    assert grade.sufficient is True and grade.score == 0.8


def test_groundedness_parses_clean_json():
    g = _grader('{"grounded": false, "score": 0.2, "reason": "hallucinated", '
                '"unsupported_spans": ["x"]}')
    grade = g.grade_groundedness("q", "a", [_sc("ctx")])
    assert grade.grounded is False and grade.unsupported_spans == ["x"]


def test_parses_json_in_code_fence():
    g = _grader('```json\n{"sufficient": true, "score": 0.9}\n```')
    assert g.grade_relevance("q", [_sc("ctx")]).sufficient is True


def test_malformed_relevance_is_fail_closed():
    g = _grader("I think the context looks pretty good honestly")  # not JSON
    grade = g.grade_relevance("q", [_sc("ctx")])
    assert grade.sufficient is False and grade.score == 0.0   # fail-closed


def test_malformed_groundedness_is_fail_closed():
    g = _grader("garbage non-json response")
    grade = g.grade_groundedness("q", "a", [_sc("ctx")])
    assert grade.grounded is False   # fail-closed: never pass on an unparseable grade


def test_empty_chunks_short_circuit_without_calling_llm():
    called = {"n": 0}
    g = OpenAICompatGrader("http://x", "m", "k")

    def _boom(system, user):
        called["n"] += 1
        raise AssertionError("must not call the LLM on empty context")

    g._complete = _boom
    assert g.grade_relevance("q", []).sufficient is False
    assert g.grade_groundedness("q", "a", []).grounded is False
    assert called["n"] == 0


@pytest.mark.llm
def test_live_grader_smoke():  # pragma: no cover - gated
    if not os.getenv("RAG_SQL_LLM_API_KEY") and not os.getenv("GROQ_API_KEY"):
        pytest.skip("no LLM API key (set GROQ_API_KEY / RAG_SQL_LLM_API_KEY)")
    key = os.getenv("GROQ_API_KEY") or os.environ["RAG_SQL_LLM_API_KEY"]
    g = OpenAICompatGrader(
        base_url=os.getenv("RAG_SQL_LLM_BASE_URL", "https://api.groq.com/openai/v1"),
        model=os.getenv("RAG_SQL_LLM_MODEL", "llama-3.3-70b-versatile"),
        api_key=key,
    )
    grade = g.grade_relevance("what is Q3 revenue",
                              [_sc("Q3 revenue was 4.2 million dollars")])
    assert grade.score >= 0.0   # a real grade came back

"""Self-RAG grader contracts + a deterministic FakeGrader (P0.8 T0).

Two judgments:
  * RELEVANCE (pre-generation): is the retrieved context good enough to answer the
    query, or should the loop take a corrective action (re-retrieve / abstain)?
  * GROUNDEDNESS (post-generation): is the generated answer SUPPORTED by the
    retrieved context, or is it (partly) hallucinated?

``Grader`` is the swappable seam: ``FakeGrader`` (rule-driven, no creds — used in
all CI tests) and ``OpenAICompatGrader`` (Groq/NVIDIA, creds-gated — WORKER-D).
The grades are typed so the loop can branch on them deterministically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..schemas import ScoredChunk

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


@dataclass(frozen=True, slots=True)
class RelevanceGrade:
    """Is the retrieved context sufficient to answer the query?"""

    sufficient: bool
    score: float          # 0..1 — overlap/confidence
    reason: str = ""


@dataclass(frozen=True, slots=True)
class GroundednessGrade:
    """Is the generated answer supported by the retrieved context?"""

    grounded: bool
    score: float          # 0..1 — fraction of answer supported by context
    reason: str = ""
    unsupported_spans: list[str] = field(default_factory=list)


@runtime_checkable
class Grader(Protocol):
    def grade_relevance(self, query: str, chunks: list[ScoredChunk]) -> RelevanceGrade: ...
    def grade_groundedness(
        self, query: str, answer: str, chunks: list[ScoredChunk]
    ) -> GroundednessGrade: ...


class FakeGrader:
    """Deterministic, no-creds grader for tests + the offline default.

    Relevance = fraction of QUERY tokens covered by the retrieved context (a cheap
    proxy for "the context is on-topic"). Groundedness = fraction of ANSWER content
    tokens present in the context (a cheap proxy for "supported, not fabricated").
    Empty retrieval is never sufficient; an answer over empty context is never
    grounded (fail-closed — you can't ground on nothing).
    """

    def __init__(
        self,
        relevance_threshold: float = 0.3,
        groundedness_threshold: float = 0.6,
    ) -> None:
        self.relevance_threshold = relevance_threshold
        self.groundedness_threshold = groundedness_threshold

    def grade_relevance(self, query: str, chunks: list[ScoredChunk]) -> RelevanceGrade:
        if not chunks:
            return RelevanceGrade(False, 0.0, "no chunks retrieved")
        q = _tokens(query)
        if not q:
            return RelevanceGrade(False, 0.0, "empty query")
        ctx = set().union(*[_tokens(c.chunk.content) for c in chunks])
        score = len(q & ctx) / len(q)
        ok = score >= self.relevance_threshold
        return RelevanceGrade(
            ok, score,
            f"query-token coverage {score:.2f} {'>=' if ok else '<'} "
            f"{self.relevance_threshold:.2f}",
        )

    def grade_groundedness(
        self, query: str, answer: str, chunks: list[ScoredChunk]
    ) -> GroundednessGrade:
        if not chunks:
            return GroundednessGrade(False, 0.0, "no context to ground on")
        a = _tokens(answer)
        if not a:
            return GroundednessGrade(False, 0.0, "empty answer")
        ctx = set().union(*[_tokens(c.chunk.content) for c in chunks])
        supported = a & ctx
        score = len(supported) / len(a)
        unsupported = sorted(a - ctx)
        ok = score >= self.groundedness_threshold
        return GroundednessGrade(
            ok, score,
            f"answer-token support {score:.2f} {'>=' if ok else '<'} "
            f"{self.groundedness_threshold:.2f}",
            unsupported_spans=unsupported,
        )

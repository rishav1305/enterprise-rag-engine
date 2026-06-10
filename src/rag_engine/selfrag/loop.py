"""CorrectiveLoop — the governance-preserving agentic self-RAG loop (P0.8 T2).

Bounded loop: retrieve -> grade relevance -> (reformulate + re-retrieve | proceed)
-> generate -> grade groundedness -> (refine | abstain | return). It abstains
fail-closed rather than fabricate, and is RESILIENT (bounded iterations + a grader
circuit breaker so a flaky grader degrades gracefully instead of hanging).

GOVERNANCE INVARIANT (the headline): the loop NEVER retrieves directly and NEVER
constructs an allowlist. It calls an injected ``retrieve_fn(query, session)`` — in
production that is the session-scoped, allowlist-pre-filtered retriever
(TurboVecRetriever.retrieve_for_session / the P0.6 mode retrievers). The loop
reformulates only the QUERY TEXT and threads the FIXED ``session`` unchanged into
every ``retrieve_fn`` call, so every iteration only ever sees authorized content.
There is structurally no path for the loop to widen a session's permissions.

Observability hooks (tracer/funnel) are optional and metric-only — each iteration
emits a step so the loop is TRANSPARENT and its stop reason is on the provenance.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..schemas import ScoredChunk, Session
from .grader import Grader, GroundednessGrade, RelevanceGrade

# Injected, session-scoped retrieval. The loop passes (reformulated_query, SESSION);
# the session is fixed for the whole run — the loop cannot change it.
RetrieveFn = Callable[[str, Session], list[ScoredChunk]]
# Query reformulation for a corrective re-retrieve: (query, iteration) -> new query.
ReformulateFn = Callable[[str, int], str]


@dataclass(slots=True)
class LoopStep:
    """One iteration's record (TRANSPARENT provenance)."""

    iteration: int
    query: str
    n_retrieved: int
    relevance_score: float
    relevance_sufficient: bool
    groundedness_score: float | None = None
    grounded: bool | None = None
    action: str = ""   # reretrieve | generate | abstain | return


@dataclass(slots=True)
class LoopResult:
    answer: str = ""
    abstained: bool = False
    iterations: int = 0
    stop_reason: str = ""   # grounded | budget_exhausted | ungrounded |
                            # insufficient_retrieval | grader_degraded
    chunks: list[ScoredChunk] = field(default_factory=list)
    steps: list[LoopStep] = field(default_factory=list)


class _Generator:
    def generate(self, query: str, admitted: list[ScoredChunk]) -> str: ...


class CorrectiveLoop:
    def __init__(
        self,
        retrieve_fn: RetrieveFn,
        generator: _Generator,
        grader: Grader,
        max_iterations: int,
        reformulate_fn: ReformulateFn | None = None,
        tracer: Any | None = None,
        funnel: Any | None = None,
        request_id: str = "",
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        self.retrieve_fn = retrieve_fn
        self.generator = generator
        self.grader = grader
        self.max_iterations = max_iterations
        # default reformulator: identity (no widening — query text unchanged).
        self.reformulate_fn = reformulate_fn or (lambda q, i: q)
        self.tracer = tracer
        self.funnel = funnel
        self.request_id = request_id

    def run(self, query: str, session: Session) -> LoopResult:
        result = LoopResult()
        current_query = query
        best: tuple[str, list[ScoredChunk]] | None = None  # best ungrounded attempt

        for i in range(1, self.max_iterations + 1):
            result.iterations = i
            # 1) RETRIEVE — session-scoped, allowlist-pre-filtered. SESSION FIXED.
            chunks = self.retrieve_fn(current_query, session)
            step = LoopStep(iteration=i, query=current_query, n_retrieved=len(chunks),
                            relevance_score=0.0, relevance_sufficient=False)

            # 2) GRADE RELEVANCE (grader circuit breaker -> graceful degrade)
            rel = self._safe(lambda: self.grader.grade_relevance(current_query, chunks))
            if rel is None:
                step.action = "grader_degraded"
                result.steps.append(step)
                self._emit(step)
                return self._degrade(result, chunks)
            step.relevance_score = rel.score
            step.relevance_sufficient = rel.sufficient

            if not rel.sufficient:
                # corrective: reformulate + re-retrieve next iteration (or abstain
                # if the budget is spent). NEVER widen permissions — query text only.
                step.action = "reretrieve"
                result.steps.append(step)
                self._emit(step)
                current_query = self.reformulate_fn(current_query, i)
                continue

            # 3) GENERATE over the (authorized) admitted context
            answer = self.generator.generate(current_query, chunks)

            # 4) GRADE GROUNDEDNESS
            gnd = self._safe(
                lambda: self.grader.grade_groundedness(current_query, answer, chunks)
            )
            if gnd is None:
                step.action = "grader_degraded"
                result.steps.append(step)
                self._emit(step)
                return self._degrade(result, chunks)
            step.groundedness_score = gnd.score
            step.grounded = gnd.grounded

            if gnd.grounded:
                step.action = "return"
                result.steps.append(step)
                self._emit(step)
                result.answer = answer
                result.chunks = chunks
                result.stop_reason = "grounded"
                return result

            # ungrounded: remember the attempt, refine + retry next iteration
            best = (answer, chunks)
            step.action = "reretrieve"
            result.steps.append(step)
            self._emit(step)
            current_query = self.reformulate_fn(current_query, i)

        # budget exhausted without a grounded answer -> ABSTAIN (fail-closed, no
        # fabrication). stop_reason records WHY (last attempt ungrounded vs never
        # sufficient) so the provenance is honest.
        result.abstained = True
        result.answer = ""
        last = result.steps[-1] if result.steps else None
        if last is not None and last.grounded is False:
            result.stop_reason = "ungrounded"
            result.chunks = best[1] if best else []
        elif last is not None and not last.relevance_sufficient:
            result.stop_reason = "insufficient_retrieval"
        else:
            result.stop_reason = "budget_exhausted"
        return result

    def _degrade(self, result: LoopResult, chunks: list[ScoredChunk]) -> LoopResult:
        """Grader failed -> abstain fail-closed (never serve on an indeterminate
        grade). The request returns, it does NOT hang."""
        result.abstained = True
        result.answer = ""
        result.stop_reason = "grader_degraded"
        return result

    @staticmethod
    def _safe(fn):
        """Grader circuit breaker: a grader raising must not crash/hang the loop."""
        try:
            return fn()
        except Exception:
            return None

    def _emit(self, step: LoopStep) -> None:
        """TRANSPARENT: emit a metric-only span + funnel note per iteration."""
        if self.tracer is not None:
            with self.tracer.span(
                "selfrag_iteration", self.request_id,
                iteration=step.iteration, n_retrieved=step.n_retrieved,
                relevance=round(step.relevance_score, 4),
                grounded=bool(step.grounded), action=step.action,
            ):
                pass
        if self.funnel is not None:
            self.funnel.stage(
                f"selfrag_iter_{step.iteration}", count=None,
                note=f"{step.action} (rel={step.relevance_score:.2f})",
            )


__all__ = ["CorrectiveLoop", "LoopResult", "LoopStep", "RetrieveFn", "ReformulateFn"]

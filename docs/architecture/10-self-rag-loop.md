# 10 — Self-RAG / corrective grading + the agentic loop

A corrective loop that re-retrieves on poor results must **never become a permission-escalation
path** — a "re-retrieve broader" step that bypassed governance would leak. CLEARANCE's loop
(`selfrag/`) is governance-preserving by construction.

## The grader (`selfrag/grader.py`)

- `RelevanceGrade` (pre-generation: is the retrieved context sufficient, or take a corrective
  action?) and `GroundednessGrade` (post-generation: is the answer supported by the context, or
  hallucinated?).
- `FakeGrader` — deterministic, no-creds (relevance = query-token coverage; groundedness =
  answer-token support; **fail-closed**: empty retrieval is never sufficient, an answer over empty
  context is never grounded). `OpenAICompatGrader` (Groq/NVIDIA, gated) parses a structured JSON
  grade **fail-closed** (malformed → not sufficient / not grounded; strict-bool — only a real JSON
  `true` passes).

## The loop (`selfrag/loop.py::CorrectiveLoop`)

Bounded: retrieve → grade-relevance → (reformulate + re-retrieve | abstain) → generate →
grade-groundedness → (refine | abstain | return). The governance invariants:

- 🔴 **The loop NEVER retrieves directly / NEVER builds an allowlist.** It calls an injected
  `retrieve_fn(query, session)` — in the pipeline, the **real session-scoped retriever**
  (`pipeline.py::_retrieve_for_session`). It reformulates the **query TEXT only** and threads the
  **fixed session** into every iteration, so every corrective re-retrieval is permission-pre-filtered.
- 🔴 **The loop self-applies `SecurityFilter` after each retrieve** (`self._security.apply`) —
  belt-and-suspenders, so even a misconfigured `retrieve_fn` can't surface raw mask/partial PII.
  (This closed a P0.8 reviewer-found bypass: the loop fed candidates to the grader/generator
  without the second governance stage.)
- **RESILIENT:** **bounded iterations** (`selfrag_max_iterations`, no infinite loop) + a **grader
  circuit breaker** (`_safe` — a grader that raises degrades gracefully → abstain, never hang; the
  swallowed error is logged, TRANSPARENT).
- **Abstain is fail-closed + honest:** budget exhausted without a grounded answer → abstain (no
  fabrication); the `LoopResult.stop_reason` (`grounded` / `ungrounded` / `insufficient_retrieval`
  / `grader_degraded`) is on the provenance.
- **TRANSPARENT:** each iteration emits a `selfrag_iteration` span + funnel note.

## Proofs

`tests/test_selfrag_governance.py` (the loop leak oracle): across ALL corrective iterations, a
denied chunk never surfaces. Mutation-proven: a `retrieve_fn` that bypasses the session pre-filter
→ leaks; remove the loop's self-redact → mask-tier PII leaks
(`tests/test_pipeline_selfrag.py`/`test_redact_multimodal.py`). `tests/test_selfrag_loop.py` proves
the bounded + circuit-breaker behavior (cap holds even if the grader always says "insufficient";
a raising grader degrades, doesn't hang).

**Wired-live vs gated:** the loop is wired into `RAGPipeline.query` (P0.11a W3, `selfrag_enabled`
default) with the real session-scoped `retrieve_fn`; the live LLM grader is gated (FakeGrader
default). The leak oracle passes **both** selfrag-on and selfrag-off (the direct L5 path is proven
too — `tests/test_pipeline_selfrag_off.py`).

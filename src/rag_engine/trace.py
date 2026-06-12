"""The glass-box ``Trace`` — the engine's REAL per-query trace (G1 spine).

This is the shared backend↔FE contract (the FE mirrors it in ``trace-types.ts``).
Field names are NORMATIVE — do not rename.

``build_trace(question, session)`` runs the REAL pipeline instrumented and assembles
the trace from its actual internals — it does NOT fork or re-narrate governance. The
un-fakeable invariant (``tests/test_trace_parity.py``): every
``trace.governance[i].decision`` equals ``access.evaluate(chunk, session).decision`` —
because both come from the SAME ``access.evaluate`` call. The ``result`` is the
persona's REDACTED view (the same ``ClientRAGResponse`` the persona would get), never
the operator governance detail.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from .config import EngineConfig
from .governance.citations import build_citations
from .observability.tracer import InMemorySpanCollector, Tracer
from .retrieval.embedders import HashingEmbedder
from .schemas import Session


# ---- the contract (normative field names) --------------------------------
class SubStep(BaseModel):
    label: str
    io_label: str
    ok: bool


class GateEval(BaseModel):
    gate: str
    result: str
    fired: bool


class Candidate(BaseModel):
    title: str
    chunk_id: str
    dense_score: float
    final_rank: int


class GovDecision(BaseModel):
    title: str
    decision: str  # allow|mask|partial|deny
    gate_fired: str
    reason: str
    required_level: int | None
    required_roles: list[str]


class Dissection(BaseModel):
    raw: str
    key_terms: list[str]
    embedding_preview: list[float]  # first 8 dims
    embedding_dim: int
    intent_shape: str
    detected_topic: str | None


class Stage(BaseModel):
    id: str
    layer: str
    label: str
    takes: str
    does: str
    pushes_out: str
    duration_ms: int
    status: str  # ok|warn
    substeps: list[SubStep]
    drilldown: dict  # {candidates:[...]} | {gates:[...]} | {loop:[...]} | {}


class Citation(BaseModel):
    title: str
    doc_hash: str
    quote: str


class TraceResult(BaseModel):
    answer: str
    citations: list[Citation]
    admitted: int
    n_withheld: int
    access_denied: bool


class Trace(BaseModel):
    query_dissection: Dissection
    stages: list[Stage]
    governance: list[GovDecision]
    result: TraceResult


# ---- the gate order access.evaluate applies (for the Governance drilldown) -
# Mirrors access.evaluate's branch order so the drilldown can mark WHICH gate fired
# per candidate. This is presentation only — the DECISION comes from access.evaluate
# (parity), never recomputed here.
_TOKEN = re.compile(r"[a-z0-9]+")


def _gate_fired_for(decision_reason: str) -> str:
    """Map a GovernanceDecision.reason to the gate label that produced it."""
    r = decision_reason
    if "public" in r:
        return "public"
    if "pii" in r:
        return "pii_class_D"
    if "unrecognized" in r:
        return "unknown_class"
    if "insufficient_clearance" in r:
        return "clearance_level"
    if "need_to_know" in r or "scoped" in r:
        return "need_to_know"
    if "role_mismatch" in r:
        return "allowed_roles"
    return "clearance_and_role"


def _span_ms(collector: InMemorySpanCollector, request_id: str, name: str) -> int:
    for sp in collector.by_request(request_id):
        if sp.name == name:
            return max(int(sp.duration_s * 1000), 0)
    return 0


def _key_terms(question: str) -> list[str]:
    seen: list[str] = []
    for t in _TOKEN.findall(question.lower()):
        if len(t) > 2 and t not in seen:
            seen.append(t)
    return seen[:12]


def build_trace(question: str, session: Session, config: EngineConfig | None = None) -> Trace:
    """Run the REAL pipeline instrumented and assemble the Trace from its internals."""
    from .pipeline import RAGPipeline  # local import: pipeline imports schemas widely

    cfg = config or EngineConfig()
    collector = InMemorySpanCollector()
    pipe = RAGPipeline(config=cfg, tracer=Tracer(collector=collector, otel=False))
    # the demo corpus path (same as the API). Caller may pre-index; if empty, index.
    if not pipe._chunks:
        from pathlib import Path
        corpus = Path(__file__).resolve().parents[2] / "corpus"
        if corpus.exists():
            pipe.index_corpus(corpus)

    request_id = pipe.tracer.new_request_id()
    architecture = pipe.router.route(question)

    # --- run the REAL retrieval + governance (the engine, not a re-narration) ---
    with pipe.tracer.span("route", request_id):
        pass
    with pipe.tracer.span("retrieve", request_id):
        candidates = pipe._retrieve_for_session(question, session)
    with pipe.tracer.span("govern", request_id, n_retrieved=len(candidates)):
        admitted, trail = pipe.security.apply(candidates, session)
    citations_admitted = build_citations(admitted, cfg)
    with pipe.tracer.span("generate", request_id, n_admitted=len(admitted)):
        if pipe.selfrag_enabled:
            answer = pipe._run_corrective_loop(question, session, request_id)
        else:
            answer = pipe.generator.generate(question, admitted)

    # --- query dissection (real tokenizer + real embedder) ---
    emb = HashingEmbedder(dim=cfg.embedding_dim)
    vec = emb.embed([question])[0]
    dissection = Dissection(
        raw=question,
        key_terms=_key_terms(question),
        embedding_preview=[round(float(x), 4) for x in vec[:8]],
        embedding_dim=cfg.embedding_dim,
        # a length HEURISTIC (not engine classification) — labeled so the FE/viewer
        # doesn't read it as a model output. The real engine classification is
        # detected_topic below (the router's architecture for this query).
        intent_shape=("short-form (heuristic)" if len(question.split()) <= 8
                      else "long-form (heuristic)"),
        detected_topic=(architecture.value if hasattr(architecture, "value") else str(architecture)),
    )

    # --- governance[] — the PARITY core: decision straight from the trail (which IS
    #     access.evaluate's output via SecurityFilter). One row per retrieved candidate. ---
    governance: list[GovDecision] = []
    for cand, dec in zip(candidates, trail):
        sec = cand.chunk.security
        governance.append(GovDecision(
            title=cand.chunk.parent_title,
            decision=dec.decision,
            gate_fired=_gate_fired_for(dec.reason),
            reason=dec.reason,
            # ENGINE-SOURCED: the chunk's real required clearance (None for public),
            # never a hardcoded table that can drift from the corpus.
            required_level=None if sec.is_public else sec.clearance_level,
            required_roles=list(dec.required_roles),
        ))

    # --- the persona's REDACTED result view (same shape ClientRAGResponse exposes) ---
    n_withheld = sum(1 for d in trail if d.decision != "allow")
    result = TraceResult(
        answer=answer,
        citations=[Citation(title=c.parent_title, doc_hash=c.doc_hash, quote=c.quote)
                   for c in citations_admitted],
        admitted=len(admitted),
        n_withheld=n_withheld,
        access_denied=(len(admitted) == 0 and len(candidates) > 0),
    )

    # --- stages (real duration_ms from the spans; drilldowns from real internals) ---
    stages = _assemble_stages(
        collector, request_id, architecture, candidates, trail, admitted, answer)

    return Trace(query_dissection=dissection, stages=stages,
                 governance=governance, result=result)


def _assemble_stages(collector, request_id, architecture, candidates, trail,
                     admitted, answer) -> list[Stage]:
    arch = architecture.value if hasattr(architecture, "value") else str(architecture)
    n_deny = sum(1 for d in trail if d.decision == "deny")
    n_mask = sum(1 for d in trail if d.decision == "mask")
    n_partial = sum(1 for d in trail if d.decision == "partial")

    # Routing
    routing = Stage(
        id="routing", layer="L3", label="Adaptive Routing",
        takes="the raw query", does="classify intent → retrieval architecture",
        pushes_out=f"architecture = {arch}",
        duration_ms=_span_ms(collector, request_id, "route"),
        status="ok",
        substeps=[SubStep(label="complexity classifier", io_label=f"→ {arch}", ok=True)],
        drilldown={},
    )

    # Retrieval — candidate scores + final rank
    cand_rows = [
        Candidate(title=c.chunk.parent_title, chunk_id=c.chunk.chunk_id,
                  dense_score=round(float(c.score), 4), final_rank=i + 1)
        for i, c in enumerate(candidates)
    ]
    retrieval = Stage(
        id="retrieval", layer="L4", label="Retrieval",
        takes="the query embedding", does="session-scoped retrieve + rerank",
        pushes_out=f"{len(candidates)} candidates",
        duration_ms=_span_ms(collector, request_id, "retrieve"),
        status="ok",
        substeps=[SubStep(label="allowlist pre-filter + rerank",
                          io_label=f"→ {len(candidates)} candidates", ok=True)],
        drilldown={"candidates": [c.model_dump() for c in cand_rows]},
    )

    # Governance — the gate-by-gate per candidate
    gate_rows = []
    for cand, dec in zip(candidates, trail):
        gate_rows.append({
            "title": cand.chunk.parent_title,
            "evals": [GateEval(gate=_gate_fired_for(dec.reason),
                               result=dec.decision, fired=True).model_dump()],
        })
    governance_stage = Stage(
        id="governance", layer="L5", label="Governance",
        takes=f"{len(candidates)} candidates + the session",
        does="access.evaluate per candidate → allow/mask/partial/deny + redact",
        pushes_out=f"{len(admitted)} admitted · {n_deny} denied · {n_mask} masked · {n_partial} partial",
        duration_ms=_span_ms(collector, request_id, "govern"),
        status="warn" if (n_deny or n_mask or n_partial) else "ok",
        substeps=[
            SubStep(label="deny → dropped before model",
                    io_label=f"{n_deny} dropped", ok=True),
            SubStep(label="mask/partial → redacted",
                    io_label=f"{n_mask + n_partial} redacted", ok=True),
        ],
        drilldown={"gates": gate_rows},
    )

    # Generation — self-RAG grades (if the loop ran)
    gen_drill: dict = {}
    loop_steps = []
    for sp in collector.by_request(request_id):
        if sp.name == "selfrag_iteration":
            loop_steps.append({"step": int(sp.attributes.get("iteration", 0)),
                               "grade": str(sp.attributes.get("action", ""))})
    if loop_steps:
        gen_drill = {"loop": loop_steps}
    generation = Stage(
        id="generation", layer="L4", label="Generation",
        takes=f"{len(admitted)} admitted (governed) chunks",
        does="generate the answer from admitted context only",
        pushes_out="the governed answer",
        duration_ms=_span_ms(collector, request_id, "generate"),
        status="ok",
        substeps=[SubStep(label="generate over admitted context",
                          io_label=f"{len(answer)} chars", ok=True)],
        drilldown=gen_drill,
    )

    return [routing, retrieval, governance_stage, generation]


__all__ = [
    "SubStep", "GateEval", "Candidate", "GovDecision", "Dissection", "Stage",
    "Citation", "TraceResult", "Trace", "build_trace",
]

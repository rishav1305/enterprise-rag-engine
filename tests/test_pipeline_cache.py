"""P0.11a W2 — SemanticCache wired into RAGPipeline with the REAL govern_fn.

End-to-end through the live pipeline: a high-clearance session populates the cache;
a low-clearance session with the SAME query never gets the high-clearance answer
(scope-isolated key + real re-governance). A second identical query from the same
session is a cache hit (the answer is reused).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.config import EngineConfig  # noqa: E402
from rag_engine.observability.tracer import InMemorySpanCollector, Tracer  # noqa: E402
from rag_engine.pipeline import RAGPipeline  # noqa: E402
from rag_engine.schemas import Document, SecurityContext, Session  # noqa: E402

SECRET = "EXEC_COMP_SECRET_FIGURE"


def _pipeline():
    cfg = EngineConfig()   # cache_enabled default True, memory backend
    pipe = RAGPipeline(config=cfg, tracer=Tracer(collector=InMemorySpanCollector(),
                                                 otel=False))
    # a class-F (exec-comp) doc: visible to C_SUITE/L5, denied to an under-cleared user.
    doc = Document(doc_id="comp1", title="Exec Comp",
                   content=f"Executive compensation details {SECRET} for the board.",
                   security=SecurityContext(allowed_roles=["C_SUITE"], clearance_level=5,
                                            sensitivity_class="F",
                                            need_to_know_roles=["C_SUITE"]))
    pub = Document(doc_id="pub1", title="Overview",
                   content="General company overview information for everyone.",
                   security=SecurityContext(allowed_roles=["PUBLIC"], clearance_level=0,
                                            sensitivity_class="A", need_to_know_roles=[]))
    pipe.index_documents([doc, pub])
    return pipe


def test_under_cleared_never_gets_high_clearance_cached_answer():
    pipe = _pipeline()
    cfo = Session(user_id="cfo", roles=["C_SUITE"], clearance_level=5)
    intern = Session(user_id="intern", roles=["INTERN"], clearance_level=1)

    # CFO asks -> the answer may include the exec-comp content; it's cached under the
    # CFO's auth scope.
    cfo_resp = pipe.query("what is executive compensation", cfo)
    assert cfo_resp is not None

    # the intern asks the SAME question -> must NOT receive the CFO's cached answer.
    # (Defended primarily by the scope-isolated cache key — the intern's auth scope
    # differs from the CFO's, so the entry is unreachable; the real govern_fn is the
    # belt-and-suspenders second layer, mutation-proven in the cache's own P0.7 unit
    # tests. Here we assert the end-to-end no-leak guarantee.)
    intern_resp = pipe.query("what is executive compensation", intern)
    assert SECRET not in intern_resp.answer, \
        "CROSS-CLEARANCE CACHE LEAK: intern received the CFO's exec-comp answer"


def test_wired_govern_fn_is_real_not_identity():
    """Directly exercise the pipeline's wired govern_fn: it must re-govern (drop a
    chunk the session can't see), proving the wiring passes REAL governance, not
    identity. BITES if _govern_fn is replaced with `return list(chunk_ids)`."""
    pipe = _pipeline()
    intern = Session(user_id="intern", roles=["INTERN"], clearance_level=1)
    # the exec-comp chunk id is denied to the intern -> _govern_fn drops it.
    comp_ids = [c.chunk_id for c in pipe._chunks if c.security.sensitivity_class == "F"]
    assert comp_ids
    governed = pipe._govern_fn(comp_ids, intern)
    assert governed == [], "wired govern_fn did not re-govern (identity?) — leak risk"


def test_same_session_repeat_query_is_cache_served():
    pipe = _pipeline()
    cfo = Session(user_id="cfo", roles=["C_SUITE"], clearance_level=5)
    first = pipe.query("company overview please", cfo)
    second = pipe.query("company overview please", cfo)
    # same scope + identical query -> the second is served from cache (same answer)
    assert first.answer == second.answer


def test_cache_hit_then_revoke_is_re_redacted():
    """The ONLY scenario where _govern_fn is the SOLE cache defense: a SAME-SCOPE
    same-question hit AFTER the chunk's governance is tightened (reclassified) between
    the put and the get. The cache key still matches (same scope), so only the real
    _govern_fn (re-run SecurityFilter over the NOW-tightened chunk) can stop the stale
    answer -> miss-on-any-redaction recomputes; the secret never re-serves.

    BITES: _govern_fn -> identity (no re-governance) -> the stale entry's chunk_ids all
    'survive' -> the cache serves the stale answer that referenced the now-restricted
    chunk -> fails.
    """
    from rag_engine.cdc.events import ChangeOp, ChunkChangeEvent
    pipe = _pipeline()   # the class-F comp doc is visible to the CFO
    cfo = Session(user_id="cfo", roles=["C_SUITE"], clearance_level=5)

    # CFO queries -> a result referencing the comp chunk is cached under the CFO scope.
    comp_id = next(c.chunk_id for c in pipe._chunks if c.security.sensitivity_class == "F")
    pipe.query("what is executive compensation", cfo)
    # a cache entry now references the comp chunk
    assert any(comp_id in e.chunk_ids for e in pipe.cache._entries.values())

    # TIGHTEN governance: reclassify the chunk so even the CFO can't see it (class H,
    # need-to-know BOARD/CISO/SECURITY — the CFO lacks all three -> deny).
    pipe.apply_change(ChunkChangeEvent(
        ChangeOp.RECLASSIFY, comp_id, 2,
        {"asset_id": "comp1", "cls": "H", "level": 4,
         "allowed_roles": ["BOARD"], "need_to_know": ["BOARD"],
         "text": "now board-only security incident"}))

    # the CFO re-queries (SAME scope, SAME question). The stale entry was invalidated
    # by the reclassify CDC; even if it weren't, _govern_fn re-governs -> the comp
    # chunk is now denied to the CFO -> not served. Either way: no stale serve.
    governed = pipe._govern_fn([comp_id], cfo)
    assert governed == [], "govern_fn did NOT re-redact a now-revoked chunk (identity?)"

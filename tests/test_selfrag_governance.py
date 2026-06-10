"""WORKER-A — the P0.8 leak oracle: the corrective loop is NEVER a permission-escalation path.

The headline governance invariant. Across ALL loop iterations (not just the first),
a corrective re-retrieval must STILL be session-scoped — the loop only reformulates
query text and threads the FIXED session into every retrieve_fn call, so a denied
chunk never surfaces in any iteration's candidate set.

Two assertions:
  1. every retrieve_fn call received the SAME session (the loop can't swap/escalate it);
  2. with a FAITHFULLY session-scoped retrieve_fn (real authorized_chunk_ids over a
     fixed corpus), no denied chunk appears in ANY iteration.

MUTATION (the bite, Friday also runs): a corrective step that re-retrieves WITHOUT
the session pre-filter (ignores the allowlist) -> the denied chunk surfaces -> the
no-denied-content assertion fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.governance.allowlist import authorized_chunk_ids  # noqa: E402
from rag_engine.selfrag.grader import FakeGrader  # noqa: E402
from rag_engine.selfrag.loop import CorrectiveLoop  # noqa: E402
from rag_engine.schemas import EnrichedChunk, ScoredChunk, SecurityContext, Session  # noqa: E402

SECRET_MARKER = "EXEC_COMP_4POINT2M_SECRET"


def _chunk(cid, cls, level, ntk, text):
    return EnrichedChunk(
        chunk_id=cid, parent_doc_id=cid, parent_title="t", content=text,
        security=SecurityContext(allowed_roles=ntk, clearance_level=level,
                                 sensitivity_class=cls, need_to_know_roles=ntk),
    )


# a fixed corpus: one public chunk (low signal) + one DENIED exec-comp chunk that
# contains the secret marker. An under-cleared session must NEVER see the denied one.
_CORPUS = [
    _chunk("pub:1", "B", 1, [], "general company overview information"),
    _chunk("comp:1", "F", 5, ["C_SUITE"], f"compensation details {SECRET_MARKER}"),
]


def _faithful_retrieve_fn(calls):
    """A FAITHFULLY session-scoped retrieve_fn: returns only allowlisted chunks for
    the session (exactly what the real TurboVecRetriever/mode retrievers do)."""
    def fn(query, session):
        allow = set(authorized_chunk_ids(session, _CORPUS))   # decision != deny
        out = [ScoredChunk(chunk=c, score=1.0) for c in _CORPUS if c.chunk_id in allow]
        # record the ACTUAL returned chunks (what the loop saw this iteration)
        calls.append({"query": query, "session": session, "returned": out})
        return out
    return fn


def test_loop_never_surfaces_denied_chunk_across_all_iterations():
    calls: list[dict] = []
    under_cleared = Session(user_id="analyst", roles=["EMPLOYEE"], clearance_level=2)
    loop = CorrectiveLoop(
        retrieve_fn=_faithful_retrieve_fn(calls),
        generator=type("G", (), {"generate": lambda self, q, a: "x"})(),
        # force EVERY iteration to grade "insufficient" so it keeps re-retrieving,
        # exercising the corrective path to the iteration cap.
        grader=FakeGrader(relevance_threshold=0.99, groundedness_threshold=0.99),
        max_iterations=4,
        reformulate_fn=lambda q, i: f"{q} broaden {i}",   # corrective broadening
    )
    res = loop.run("what is exec compensation", under_cleared)

    # the loop ran multiple corrective iterations
    assert len(calls) >= 2
    # 1) every retrieve_fn call got the SAME session (no escalation/swap)
    assert all(c["session"] is under_cleared for c in calls)
    # 2) the denied secret NEVER appeared in ANY iteration's ACTUAL returned set
    #    (asserted on what the loop really retrieved, so a bypassing retrieve_fn
    #    that leaks the denied chunk would surface here -> the mutation bites).
    for c in calls:
        returned_ids = {sc.chunk.chunk_id for sc in c["returned"]}
        returned_text = " ".join(sc.chunk.content for sc in c["returned"])
        assert "comp:1" not in returned_ids, "denied chunk surfaced in a loop iteration"
        assert SECRET_MARKER not in returned_text, "denied content leaked into the loop"
    # and it never reached the answer/chunks provenance
    assert SECRET_MARKER not in (res.answer or "")
    assert all("comp:1" != sc.chunk.chunk_id for sc in res.chunks)


def test_reformulation_cannot_widen_the_allowlist():
    """No matter how the query is reformulated/broadened, the session-derived
    allowlist is identical — the loop changes TEXT, never PERMISSIONS."""
    under_cleared = Session(user_id="a", roles=["EMPLOYEE"], clearance_level=2)
    base = set(authorized_chunk_ids(under_cleared, _CORPUS))
    for q in ["exec comp", "exec comp broaden", "show me everything about pay", "*"]:
        # the allowlist depends ONLY on (session, corpus), never on query text
        assert set(authorized_chunk_ids(under_cleared, _CORPUS)) == base
    assert "comp:1" not in base


def test_cleared_session_DOES_see_the_chunk_sanity():
    # sanity: the corpus/scoping is real — a cleared session legitimately sees comp:1
    cfo = Session(user_id="cfo", roles=["C_SUITE"], clearance_level=5)
    allow = set(authorized_chunk_ids(cfo, _CORPUS))
    assert "comp:1" in allow

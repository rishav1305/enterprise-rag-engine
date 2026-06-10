"""P0.6 — AllowlistBackend ABC + InProcessAllowlist (the swappable engine).

InProcessAllowlist is the reference/default engine: it MUST agree exactly with
the canonical ``authorized_chunk_ids`` (decision != deny). The ABC contract is
what the ReBAC backends (SpiceDB, Oso) are parity-tested against — so this file
locks the reference behaviour the whole P0.6 phase hangs on.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.governance.allowlist import (  # noqa: E402
    AllowlistBackend,
    InProcessAllowlist,
    authorized_chunk_ids,
)
from rag_engine.schemas import EnrichedChunk, SecurityContext, Session  # noqa: E402


def _chunk(cid, cls, level, ntk):
    return EnrichedChunk(
        chunk_id=cid, parent_doc_id=cid, parent_title="t", content="x",
        security=SecurityContext(allowed_roles=ntk, clearance_level=level,
                                 sensitivity_class=cls, need_to_know_roles=ntk),
    )


def _matrix():
    return [
        _chunk("c:pub", "B", 1, []),         # public  -> allow for everyone
        _chunk("c:pii", "D", 3, []),         # PII     -> needs clearance 3
        _chunk("c:comp", "F", 5, ["C_SUITE"]),  # exec-comp -> NTK C_SUITE + clr 5
    ]


def test_inprocess_satisfies_abc():
    assert isinstance(InProcessAllowlist(), AllowlistBackend)


def test_inprocess_allowlist_equals_canonical():
    # Across a spread of sessions, the backend must equal the canonical function.
    chunks = _matrix()
    backend = InProcessAllowlist()
    sessions = [
        Session(user_id="analyst", roles=["EMPLOYEE"], clearance_level=2),
        Session(user_id="exec", roles=["C_SUITE"], clearance_level=5),
        Session(user_id="mgr", roles=["MANAGER"], clearance_level=3),
    ]
    for s in sessions:
        assert backend.authorized_ids(s, chunks) == authorized_chunk_ids(s, chunks)


def test_inprocess_denies_overclassified():
    chunks = _matrix()
    analyst = Session(user_id="a", roles=["EMPLOYEE"], clearance_level=2)
    allow = InProcessAllowlist().authorized_ids(analyst, chunks)
    assert "c:comp" not in allow   # exec-comp -> DENY (NTK C_SUITE + clearance 5)
    # c:pii is class-D at clearance 2 -> MASK (retrievable-but-redacted), so it
    # stays ON the allowlist by design (the redaction happens downstream). The
    # allowlist excludes ONLY deny — this is the pre/post-filter consistency invariant.
    assert "c:pii" in allow
    assert "c:pub" in allow        # public retrievable


def test_order_preserving():
    chunks = _matrix()
    exec_sess = Session(user_id="e", roles=["C_SUITE"], clearance_level=5)
    allow = InProcessAllowlist().authorized_ids(exec_sess, chunks)
    # exec sees all three, in candidate order
    assert allow == ["c:pub", "c:pii", "c:comp"]


def test_backend_injection_through_wrapper():
    # The wrapper routes to an injected backend (the seam ReBAC plugs into).
    chunks = _matrix()
    s = Session(user_id="e", roles=["C_SUITE"], clearance_level=5)
    assert authorized_chunk_ids(s, chunks, backend=InProcessAllowlist()) == \
        authorized_chunk_ids(s, chunks)

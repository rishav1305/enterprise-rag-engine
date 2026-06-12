"""G0 — the enriched corpus makes mask + partial governance LIVE.

Today's 4-doc corpus only yields allow/deny. G0 adds:
  * a class-D customer-PII doc -> `mask` at L2-L3 ([REDACTED]), raw at L4+;
  * a partial-scope doc -> `partial` for out-of-scope roles ([PARTIAL …]).

These are the live mask/partial cells the glass-box trace must show. The 210-cell
oracle (seed access_matrix) is unaffected; these tests govern the corpus docs through
the real `access.evaluate` + `redact_chunk`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.governance import access  # noqa: E402
from rag_engine.governance.filter import SecurityFilter  # noqa: E402
from rag_engine.ingestion.markdown_loader import MarkdownLoader, chunk_document  # noqa: E402
from rag_engine.schemas import ScoredChunk, Session  # noqa: E402

_CORPUS = Path(__file__).resolve().parents[1] / "corpus"


def _chunks_for(doc_id: str):
    docs = MarkdownLoader(_CORPUS).load()
    doc = next(d for d in docs if d.doc_id == doc_id)
    return chunk_document(doc)


# ---- class-D customer-PII doc -> MASK at L2-L3 ----------------------------
def test_customer_doc_is_class_d():
    chunks = _chunks_for("customer-account-sample")
    assert chunks and all(c.security.sensitivity_class == "D" for c in chunks)


def test_under_cleared_session_masks_customer_pii():
    chunks = _chunks_for("customer-account-sample")
    l2 = Session(user_id="analyst", roles=["DATA_ANALYST", "EMPLOYEE"], clearance_level=2)
    # class-D @ L2 -> mask (admitted-but-redacted)
    for c in chunks:
        assert access.evaluate(c, l2).decision == "mask"
    admitted, trail = SecurityFilter().apply(
        [ScoredChunk(chunk=c, score=1.0) for c in chunks], l2)
    assert {d.decision for d in trail} == {"mask"}
    assert admitted and all(sc.chunk.content == "[REDACTED]" for sc in admitted)


def test_cleared_session_sees_raw_customer_pii():
    chunks = _chunks_for("customer-account-sample")
    # L4+ -> allow (raw)
    cfo = Session(user_id="cfo", roles=["C_SUITE", "FINANCE"], clearance_level=5)
    for c in chunks:
        assert access.evaluate(c, cfo).decision == "allow"


def test_below_l2_denies_customer_pii():
    chunks = _chunks_for("customer-account-sample")
    intern = Session(user_id="intern", roles=["INTERN", "EMPLOYEE"], clearance_level=1)
    for c in chunks:
        assert access.evaluate(c, intern).decision == "deny"


# ---- partial-scope doc -> PARTIAL for out-of-scope roles ------------------
def test_dept_doc_partial_for_out_of_scope_role():
    chunks = _chunks_for("dept-scoped-record")
    # a session whose role is NOT the need-to-know role but IS in partial_for ->
    # row-scoped PARTIAL (admitted with a scope predicate, content withheld token).
    scoped = Session(user_id="oncall", roles=["ON_CALL"], clearance_level=2)
    for c in chunks:
        dec = access.evaluate(c, scoped)
        assert dec.decision == "partial", f"expected partial, got {dec.decision}"
    admitted, trail = SecurityFilter().apply(
        [ScoredChunk(chunk=c, score=1.0) for c in chunks], scoped)
    assert {d.decision for d in trail} == {"partial"}
    assert admitted and all("[PARTIAL" in sc.chunk.content for sc in admitted)


def test_dept_doc_full_role_sees_it():
    chunks = _chunks_for("dept-scoped-record")
    # the full need-to-know role -> allow.
    owner = Session(user_id="eng", roles=["ENGINEERING"], clearance_level=3)
    for c in chunks:
        assert access.evaluate(c, owner).decision == "allow"


def test_dept_doc_unrelated_role_denied():
    chunks = _chunks_for("dept-scoped-record")
    # neither need-to-know nor partial-scope -> deny.
    other = Session(user_id="hr", roles=["HR"], clearance_level=3)
    for c in chunks:
        assert access.evaluate(c, other).decision == "deny"

"""G0 hardening (reviewer fixes) — fail-open close + non-vacuous mask/partial proofs.

FIX 1: a malformed/unknown sensitivity_class must NOT fall through to allow (the
       legacy role gate was `if not cls` — a non-empty unknown class skipped it).
FIX 2/3: the class-D mask proof must be LOAD-BEARING on the raw PII string + the
       L3/L4 boundary must bite.
FIX 4/5: loader propagation, fail-closed default, partial precedence + below-level,
       and the class-D-must-be-L2+ validator.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rag_engine.governance import access  # noqa: E402
from rag_engine.governance.filter import SecurityFilter  # noqa: E402
from rag_engine.ingestion.markdown_loader import MarkdownLoader, chunk_document  # noqa: E402
from rag_engine.schemas import EnrichedChunk, ScoredChunk, SecurityContext, Session  # noqa: E402

_CORPUS = Path(__file__).resolve().parents[1] / "corpus"
RAW_PII = "dana.okafor@example.com"   # the raw value that must never leak below L4


def _chunks_for(doc_id: str):
    docs = MarkdownLoader(_CORPUS).load()
    doc = next(d for d in docs if d.doc_id == doc_id)
    return chunk_document(doc)


def _chunk(cls, level, *, allowed=None, ntk=None, content="x"):
    return EnrichedChunk(
        chunk_id="c", parent_doc_id="d", parent_title="t", content=content,
        security=SecurityContext(allowed_roles=allowed or [], clearance_level=level,
                                 sensitivity_class=cls, need_to_know_roles=ntk or []),
    )


# ---- FIX 1: fail-open close (defense-in-depth in access.evaluate) ---------
@pytest.mark.parametrize("bad", ["d", "ZZ", "x", "dd", "1"])
def test_unknown_class_fails_closed_not_open(bad):
    # a level-passing, role-disjoint session: the legacy gate used to bypass on a
    # non-empty unknown class -> allow. It must now DENY (fail-closed).
    ch = _chunk(bad, 3, allowed=["CUSTOMER_DATA_STEWARD"], content=f"SSN {RAW_PII}")
    s = Session(user_id="a", roles=["DATA_ANALYST"], clearance_level=3)
    assert access.evaluate(ch, s).decision == "deny"


def test_lowercase_d_does_not_leak_raw_pii():
    # the typo case the reviewer flagged: a 'd' (not 'D') PII doc must not serve raw.
    ch = _chunk("d", 3, content=f"SSN {RAW_PII}")
    s = Session(user_id="b", roles=["DATA_ANALYST"], clearance_level=3)
    dec = access.evaluate(ch, s)
    assert dec.decision == "deny"   # unrecognized class -> fail-closed (loader rejects 'd' anyway)


def test_valid_classes_still_flow(  # regression: the fix must NOT break A-N
):
    # public A
    assert access.evaluate(_chunk("A", 0), Session(user_id="i", roles=["INTERN"], clearance_level=1)).decision == "allow"
    # class-D mask at L3
    assert access.evaluate(_chunk("D", 3), Session(user_id="a", roles=["X"], clearance_level=3)).decision == "mask"
    # class-F deny for under-cleared
    assert access.evaluate(_chunk("F", 5, ntk=["C_SUITE"]), Session(user_id="x", roles=["EMPLOYEE"], clearance_level=2)).decision == "deny"


# ---- FIX 1a: loader rejects a malformed class at ingest ------------------
def test_loader_rejects_unknown_class(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text(
        "---\ndoc_id: bad\nallowed_roles: []\nclearance_level: 3\n"
        "sensitivity_class: zz\n---\nbody\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sensitivity_class"):
        MarkdownLoader(tmp_path).load()


def test_loader_normalizes_lowercase_class(tmp_path):
    # a lowercase 'd' must be normalized to 'D' (the auto-fix for the typo case).
    doc = tmp_path / "cust.md"
    doc.write_text(
        "---\ndoc_id: cust\nallowed_roles: []\nclearance_level: 3\n"
        "sensitivity_class: d\n---\nbody\n", encoding="utf-8")
    loaded = MarkdownLoader(tmp_path).load()
    assert loaded[0].security.sensitivity_class == "D"


# ---- FIX 2/3: the class-D PII proof is LOAD-BEARING + the L3/L4 boundary --
def test_l3_masks_and_raw_pii_absent():
    chunks = _chunks_for("customer-account-sample")
    l3 = Session(user_id="s", roles=["SALES_MANAGER", "EMPLOYEE"], clearance_level=3)
    admitted, trail = SecurityFilter().apply([ScoredChunk(chunk=c, score=1.0) for c in chunks], l3)
    assert {d.decision for d in trail} == {"mask"}
    blob = " ".join(sc.chunk.content for sc in admitted)
    assert RAW_PII not in blob, "L3 LEAK: raw PII present in masked content"


def test_l4_raw_and_raw_pii_present():
    chunks = _chunks_for("customer-account-sample")
    l4 = Session(user_id="d", roles=["DIRECTOR"], clearance_level=4)
    admitted, trail = SecurityFilter().apply([ScoredChunk(chunk=c, score=1.0) for c in chunks], l4)
    assert {d.decision for d in trail} == {"allow"}
    blob = " ".join(sc.chunk.content for sc in admitted)
    assert RAW_PII in blob, "L4+ should receive the RAW PII (the boundary must be real)"


# ---- FIX 4: loader propagation, fail-closed default, partial precedence ---
def test_loader_propagates_ntk_and_partial_for():
    chunks = _chunks_for("dept-scoped-record")
    for c in chunks:
        assert c.security.need_to_know_roles == ["ENGINEERING"]
        assert c.metadata["partial_for"] == ["ON_CALL"]


def test_unclassed_doc_loads_fail_closed_defaults(tmp_path):
    doc = tmp_path / "plain.md"
    doc.write_text(
        "---\ndoc_id: plain\nallowed_roles: [FINANCE]\nclearance_level: 2\n---\nbody\n",
        encoding="utf-8")
    chunks = chunk_document(MarkdownLoader(tmp_path).load()[0])
    c = chunks[0]
    assert c.security.sensitivity_class == ""
    assert c.security.need_to_know_roles == []
    assert c.metadata == {}


def test_partial_precedence_full_role_wins():
    chunks = _chunks_for("dept-scoped-record")
    # dual-role: ENGINEERING (full) + ON_CALL (partial) -> ALLOW (full wins).
    dual = Session(user_id="e", roles=["ENGINEERING", "ON_CALL"], clearance_level=3)
    for c in chunks:
        assert access.evaluate(c, dual).decision == "allow"


def test_partial_below_level_denied():
    chunks = _chunks_for("dept-scoped-record")
    # ON_CALL @ L1 (below the doc's L2) -> deny (level gate fires before partial).
    low = Session(user_id="o", roles=["ON_CALL"], clearance_level=1)
    for c in chunks:
        assert access.evaluate(c, low).decision == "deny"


# ---- FIX 5: a class-D / PII doc must declare clearance_level >= 2 ---------
def test_class_d_public_misconfig_rejected(tmp_path):
    # a class-D doc misconfigured as level-0 PUBLIC would short-circuit is_public ->
    # leak raw PII to anon before the mask leg. The loader must refuse it.
    doc = tmp_path / "leak.md"
    doc.write_text(
        "---\ndoc_id: leak\nallowed_roles: [PUBLIC]\nclearance_level: 0\n"
        "sensitivity_class: D\n---\nbody\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clearance"):
        MarkdownLoader(tmp_path).load()

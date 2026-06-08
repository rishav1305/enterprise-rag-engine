"""P0.1b — governance-v2 tests (masking, class-aware access, partial, filter)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.governance.masking import MaskReason, mask_value  # noqa: E402


def test_mask_value_redacts_pii():
    assert mask_value("jane@example.com", MaskReason.PII_MASK) == "[REDACTED]"


def test_mask_value_field_acl_shows_type_not_value():
    assert mask_value(125000, MaskReason.FIELD_ACL_MASK) == "[RESTRICTED]"


def test_mask_reason_values():
    assert MaskReason.PII_MASK.value == "pii_mask"
    assert MaskReason.FIELD_ACL_MASK.value == "field_acl_mask"


# ---- Task 5: SecurityContext + GovernanceDecision extensions -----------
def test_security_context_carries_class_and_need_to_know():
    from rag_engine.schemas import SecurityContext
    sc = SecurityContext(
        allowed_roles=["FINANCE", "C_SUITE"], clearance_level=4,
        sensitivity_class="E", need_to_know_roles=["FINANCE", "C_SUITE"],
    )
    assert sc.sensitivity_class == "E"
    assert "FINANCE" in sc.need_to_know_roles


def test_governance_decision_supports_mask():
    from rag_engine.schemas import GovernanceDecision
    d = GovernanceDecision(chunk_id="c1", parent_doc_id="d1", decision="mask",
                           reason="pii", mask_reason="pii_mask")
    assert d.decision == "mask"
    assert d.mask_reason == "pii_mask"


def test_governance_decision_supports_partial():
    from rag_engine.schemas import GovernanceDecision
    d = GovernanceDecision(chunk_id="c1", parent_doc_id="d1", decision="partial",
                           reason="scoped", scope="own_component")
    assert d.decision == "partial"
    assert d.scope == "own_component"


# ---- Task 6: class-aware access (allow/mask/deny + non-monotonic) -------
def _chunk(cls, roles, level, ntk=None, meta=None):
    from rag_engine.schemas import EnrichedChunk, SecurityContext
    return EnrichedChunk(
        chunk_id="c1", parent_doc_id=f"asset-{cls}", parent_title="t", content="x",
        security=SecurityContext(allowed_roles=roles, clearance_level=level,
                                 sensitivity_class=cls,
                                 need_to_know_roles=ntk if ntk is not None else roles),
        metadata=meta or {},
    )


def _sess(roles, level):
    from rag_engine.schemas import Session
    return Session(user_id="u", roles=roles, clearance_level=level)


def test_access_masks_customer_pii_for_analyst():
    from rag_engine.governance.access import evaluate
    chunk = _chunk("D", ["EMPLOYEE"], 3)
    analyst = _sess(["MARKETING_ANALYST", "EMPLOYEE"], 2)
    assert evaluate(chunk, analyst).decision == "mask"
    intern = _sess(["INTERN", "EMPLOYEE"], 1)
    assert evaluate(chunk, intern).decision == "deny"
    director = _sess(["FINANCE", "EMPLOYEE"], 4)
    assert evaluate(chunk, director).decision == "allow"  # raw at L4+


def test_access_non_monotonic_finance_manager_class_F():
    from rag_engine.governance.access import evaluate
    chunk = _chunk("F", ["C_SUITE"], 5, ntk=["C_SUITE"])
    fm = _sess(["FINANCE", "FINANCE_MANAGER", "EMPLOYEE"], 4)
    assert evaluate(chunk, fm).decision == "deny"  # high level, wrong need-to-know


def test_access_finance_manager_sees_class_E():
    from rag_engine.governance.access import evaluate
    chunk = _chunk("E", ["FINANCE", "C_SUITE"], 4, ntk=["FINANCE", "C_SUITE"])
    fm = _sess(["FINANCE", "FINANCE_MANAGER", "EMPLOYEE"], 4)
    assert evaluate(chunk, fm).decision == "allow"
    legal = _sess(["LEGAL", "EMPLOYEE"], 4)
    assert evaluate(chunk, legal).decision == "deny"  # L4 but no FINANCE need-to-know


# ---- Task 7: PARTIAL decision (Engineer / class H scoped) ---------------
def test_engineer_partial_access_to_security_class_H():
    from rag_engine.governance.access import evaluate
    chunk = _chunk(
        "H", ["CISO", "SECURITY", "BOARD", "ENGINEER"], 2,
        ntk=["CISO", "SECURITY", "BOARD"],
        meta={"partial_for": ["ENGINEER"]},
    )
    eng = _sess(["ENGINEER", "EMPLOYEE"], 2)
    d = evaluate(chunk, eng)
    assert d.decision == "partial"
    assert d.scope == "own_component"


def test_ciso_gets_full_access_not_partial():
    from rag_engine.governance.access import evaluate
    chunk = _chunk(
        "H", ["CISO", "SECURITY", "BOARD", "ENGINEER"], 4,
        ntk=["CISO", "SECURITY", "BOARD"],
        meta={"partial_for": ["ENGINEER"]},
    )
    ciso = _sess(["CISO", "SECURITY", "EMPLOYEE"], 4)
    assert evaluate(chunk, ciso).decision == "allow"


def test_partial_vs_full_precedence_full_wins():
    # A session holding BOTH a full need-to-know role AND a partial role must get
    # full ALLOW, never downgraded to partial (Batch B review Minor).
    from rag_engine.governance.access import evaluate
    chunk = _chunk(
        "H", ["CISO", "SECURITY", "BOARD", "ENGINEER"], 2,
        ntk=["CISO", "SECURITY", "BOARD"],
        meta={"partial_for": ["ENGINEER"]},
    )
    dual = _sess(["ENGINEER", "SECURITY", "EMPLOYEE"], 4)
    assert evaluate(chunk, dual).decision == "allow"


def test_non_partial_session_still_denied():
    # Neither full nor partial role -> denied (fail-closed).
    from rag_engine.governance.access import evaluate
    chunk = _chunk(
        "H", ["CISO", "SECURITY", "BOARD", "ENGINEER"], 2,
        ntk=["CISO", "SECURITY", "BOARD"],
        meta={"partial_for": ["ENGINEER"]},
    )
    analyst = _sess(["DATA_ANALYST", "EMPLOYEE"], 2)
    assert evaluate(chunk, analyst).decision == "deny"


# ---- Task 8: filter admits mask/partial, drops only deny ----------------
def test_filter_admits_masked_chunk_not_dropped():
    from rag_engine.governance.filter import SecurityFilter
    from rag_engine.schemas import ScoredChunk
    pii = ScoredChunk(chunk=_chunk("D", ["EMPLOYEE"], 3), score=1.0)
    analyst = _sess(["MARKETING_ANALYST", "EMPLOYEE"], 2)
    admitted, trail = SecurityFilter().apply([pii], analyst)
    assert len(admitted) == 1            # masked chunk ADMITTED, not dropped
    assert trail[0].decision == "mask"


def test_filter_admits_partial_chunk():
    from rag_engine.governance.filter import SecurityFilter
    from rag_engine.schemas import ScoredChunk
    h = ScoredChunk(chunk=_chunk("H", ["CISO", "SECURITY", "BOARD", "ENGINEER"], 2,
                                 ntk=["CISO", "SECURITY", "BOARD"],
                                 meta={"partial_for": ["ENGINEER"]}), score=1.0)
    eng = _sess(["ENGINEER", "EMPLOYEE"], 2)
    admitted, trail = SecurityFilter().apply([h], eng)
    assert len(admitted) == 1
    assert trail[0].decision == "partial"


def test_filter_drops_only_deny():
    from rag_engine.governance.filter import SecurityFilter
    from rag_engine.schemas import ScoredChunk
    allow_c = ScoredChunk(chunk=_chunk("B", ["EMPLOYEE"], 1), score=1.0)
    deny_c = ScoredChunk(chunk=_chunk("F", ["C_SUITE"], 5, ntk=["C_SUITE"]), score=1.0)
    mask_c = ScoredChunk(chunk=_chunk("D", ["EMPLOYEE"], 3), score=1.0)
    sess = _sess(["MARKETING_ANALYST", "EMPLOYEE"], 2)
    admitted, trail = SecurityFilter().apply([allow_c, deny_c, mask_c], sess)
    decisions = [d.decision for d in trail]
    assert decisions == ["allow", "deny", "mask"]
    assert len(admitted) == 2  # allow + mask admitted; deny dropped


def test_filter_carries_mask_reason_in_trail():
    from rag_engine.governance.filter import SecurityFilter
    from rag_engine.schemas import ScoredChunk
    pii = ScoredChunk(chunk=_chunk("D", ["EMPLOYEE"], 3), score=1.0)
    analyst = _sess(["MARKETING_ANALYST", "EMPLOYEE"], 2)
    _, trail = SecurityFilter().apply([pii], analyst)
    assert trail[0].mask_reason == "pii_mask"

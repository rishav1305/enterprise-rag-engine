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

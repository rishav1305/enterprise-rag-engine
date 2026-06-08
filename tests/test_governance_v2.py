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

"""Column masking — the two distinct mask reasons + value redaction.

``PII_MASK``      — personal data redaction (e.g. customer email, KYC gov_id).
``FIELD_ACL_MASK`` — a role-secured field that is not PII (e.g. CRM ``deal_value``,
                     procurement ``terms_value``). Distinguishing the two lets the
                     audit trail explain *why* a column was withheld (TRANSPARENT).

``mask_value`` never returns the original value — masking is fail-closed.
"""

from __future__ import annotations

from enum import Enum


class MaskReason(str, Enum):
    PII_MASK = "pii_mask"
    FIELD_ACL_MASK = "field_acl_mask"


_REDACTIONS: dict[MaskReason, str] = {
    MaskReason.PII_MASK: "[REDACTED]",
    MaskReason.FIELD_ACL_MASK: "[RESTRICTED]",
}


def mask_value(value: object, reason: MaskReason) -> str:
    """Replace a value with its redaction token. Never returns the original."""
    return _REDACTIONS[reason]

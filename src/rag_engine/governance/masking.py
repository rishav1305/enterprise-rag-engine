"""Column masking — the two distinct mask reasons + value redaction + chunk redaction.

``PII_MASK``      — personal data redaction (e.g. customer email, KYC gov_id).
``FIELD_ACL_MASK`` — a role-secured field that is not PII (e.g. CRM ``deal_value``,
                     procurement ``terms_value``). Distinguishing the two lets the
                     audit trail explain *why* a column was withheld (TRANSPARENT).

``mask_value`` never returns the original value — masking is fail-closed.
``redact_chunk`` rewrites an admitted chunk's content so the model + citations
only ever see the redaction token — the ENFORCEMENT half of governance-v2.
"""

from __future__ import annotations

from enum import Enum

from ..schemas import EnrichedChunk, GovernanceDecision, ScoredChunk


class MaskReason(str, Enum):
    PII_MASK = "pii_mask"
    FIELD_ACL_MASK = "field_acl_mask"


_REDACTIONS: dict[MaskReason, str] = {
    MaskReason.PII_MASK: "[REDACTED]",
    MaskReason.FIELD_ACL_MASK: "[RESTRICTED]",
}

# Decision-level redaction tokens (chunk-grain enforcement). Until column-grain
# selective masking lands (real columnar rows in P0.2a), a masked chunk's whole
# content is replaced with the token so no raw value can reach the model.
_PARTIAL_TOKEN = "[PARTIAL — scoped access; full content withheld]"


def mask_value(value: object, reason: MaskReason) -> str:
    """Replace a value with its redaction token. Never returns the original."""
    return _REDACTIONS[reason]


def _token_for(decision: GovernanceDecision) -> str:
    if decision.decision == "mask":
        try:
            return mask_value(None, MaskReason(decision.mask_reason or "pii_mask"))
        except ValueError:
            return _REDACTIONS[MaskReason.PII_MASK]
    if decision.decision == "partial":
        return _PARTIAL_TOKEN
    return ""


def redact_chunk(sc: ScoredChunk, decision: GovernanceDecision) -> ScoredChunk:
    """Return a ScoredChunk whose content is redacted per the decision.

    ``allow`` passes through unchanged. ``mask``/``partial`` get content replaced
    with the redaction token so generation + citations never see the raw value.
    Fail-closed: an unknown non-allow decision is treated as a full redaction.

    P0.10 — NON-TEXT (image/table/ocr/figure): you can't ``[REDACTED]`` a pixel
    inline, so a masked non-text chunk is WITHHELD: the raw payload is stripped from
    metadata and the content becomes a modality-aware withhold token. Without this,
    copying ``metadata`` verbatim would leak the raw image/table bytes past a mask.
    """
    if decision.decision == "allow":
        return sc

    modality = getattr(sc.chunk, "modality", "text")

    if modality != "text":
        # WITHHOLD the raw payload (the enforcement half for non-text). Deep-copy +
        # scrub the metadata down to a scalar allowlist so NO payload survives
        # anywhere (a sidecar key / nested thumbnail / structured table), and the
        # redacted chunk aliases no mutable object from the original.
        from ..multimodal.payload import scrub_metadata_for_withhold

        metadata = scrub_metadata_for_withhold(sc.chunk.metadata)
        base = _token_for(decision) or _REDACTIONS[MaskReason.PII_MASK]
        token = f"{base} [{modality} withheld]"
    else:
        # text: shallow copy is fine (content is a string, no nested payload).
        metadata = dict(sc.chunk.metadata)
        token = _token_for(decision) or _REDACTIONS[MaskReason.PII_MASK]

    redacted = EnrichedChunk(
        chunk_id=sc.chunk.chunk_id,
        parent_doc_id=sc.chunk.parent_doc_id,
        parent_title=sc.chunk.parent_title,
        content=token,
        contextual_anchor="",  # drop the anchor too — it may echo raw content
        security=sc.chunk.security,
        ordinal=sc.chunk.ordinal,
        modality=modality,
        metadata=metadata,
    )
    return ScoredChunk(
        chunk=redacted, score=sc.score,
        lexical_rank=sc.lexical_rank, dense_rank=sc.dense_rank,
    )

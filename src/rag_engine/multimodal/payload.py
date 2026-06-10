"""Multimodal payload convention (P0.10 T0).

A non-text chunk's binary/structured payload (image bytes, table rows, raw OCR
source) lives in ``EnrichedChunk.metadata`` under ONE conventional key. Centralising
it means redaction (``governance.masking.redact_chunk``) has a single place to
WITHHOLD the raw payload for a masked/partial non-text chunk — no payload can hide in
a per-modality metadata field the redactor forgot about.
"""

from __future__ import annotations

from typing import Any

# The single metadata key every modality's raw payload lives under.
MULTIMODAL_PAYLOAD_KEY = "mm_payload"


def attach_payload(metadata: dict[str, Any], payload: Any) -> dict[str, Any]:
    """Store a raw payload (bytes / structured rows) on a chunk's metadata."""
    metadata[MULTIMODAL_PAYLOAD_KEY] = payload
    return metadata


def get_payload(metadata: dict[str, Any] | None) -> Any | None:
    """Return the raw payload, or None if absent."""
    if not metadata:
        return None
    return metadata.get(MULTIMODAL_PAYLOAD_KEY)


def strip_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    """Remove the raw payload (the WITHHOLD half of non-text masking). Idempotent."""
    metadata.pop(MULTIMODAL_PAYLOAD_KEY, None)
    return metadata

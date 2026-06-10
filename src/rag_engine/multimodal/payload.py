"""Multimodal payload convention (P0.10 T0).

A non-text chunk's binary/structured payload (image bytes, table rows, raw OCR
source) lives in ``EnrichedChunk.metadata`` under ONE conventional key. Centralising
it means redaction (``governance.masking.redact_chunk``) has a single place to
WITHHOLD the raw payload for a masked/partial non-text chunk — no payload can hide in
a per-modality metadata field the redactor forgot about.
"""

from __future__ import annotations

import copy
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
    """Remove the conventional raw payload key (the cheap, common path). Idempotent.

    NOTE: this only drops MULTIMODAL_PAYLOAD_KEY. For the REDACTION withhold contract
    ("no raw payload ANYWHERE"), use ``scrub_metadata_for_withhold`` instead, which
    deep-copies + removes binary values wherever they hide (a sidecar key, a nested
    thumbnail dict, etc.). Live extractors that store thumbnails/crops are exactly the
    case that needs the recursive scrub.
    """
    metadata.pop(MULTIMODAL_PAYLOAD_KEY, None)
    return metadata


# Metadata keys safe to KEEP on a withheld non-text chunk — scalar provenance only,
# never anything that could carry a raw payload (bytes, image crops, table rows).
# A withheld chunk keeps just enough to remain explainable (which modality, where it
# came from); everything else is dropped. Allowlist (not denylist) so a NEW sidecar
# key a future live extractor adds is withheld by DEFAULT (fail-closed).
_WITHHOLD_KEEP_KEYS = frozenset({"modality", "source_uri", "page", "ordinal", "caption"})


def _is_scalar(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool)) or v is None


def scrub_metadata_for_withhold(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Deep-copy ``metadata`` down to a known-safe SCALAR allowlist for a withheld
    non-text chunk.

    The withhold contract is "no raw payload ANYWHERE" — so rather than chase every
    place a payload could hide (a sidecar key, a nested thumbnail dict, a structured
    table), we KEEP only an allowlist of scalar provenance fields and DROP everything
    else (bytes, dicts, lists — anything that could carry a payload). Fail-closed: an
    unknown key is dropped by default. Returns a fresh dict sharing no mutable object
    with the original (deep-copied scalars).
    """
    if not metadata:
        return {}
    return {
        k: copy.deepcopy(v)
        for k, v in metadata.items()
        if k in _WITHHOLD_KEEP_KEYS and _is_scalar(v)
    }

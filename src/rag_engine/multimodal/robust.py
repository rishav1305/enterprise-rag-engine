"""Multimodal robustness (P0.10 WORKER-D) — bounded, audited, TRANSPARENT.

Extraction touches untrusted binaries (scanned PDFs, images), so it must be:
  * RESILIENT — an extractor crash does NOT crash ingest; it yields no chunks and the
    failure is AUDITED (a silent drop would hide a data-integrity gap);
  * ELASTIC — a payload over a configured bound is rejected (bounded binary footprint
    — a giant upload can't blow memory), also audited.

``guarded_extract`` wraps any ``ModalityExtractor`` with both guards.
"""

from __future__ import annotations

import logging
from typing import Any

from ..schemas import Document, EnrichedChunk

_log = logging.getLogger(__name__)

# Default cap on a single extraction payload (bytes). CONFIGURABLE by the caller.
DEFAULT_MAX_PAYLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB


class PayloadTooLarge(Exception):
    """Raised when a payload exceeds the configured size bound (ELASTIC)."""


def _size_of(raw: Any) -> int:
    if isinstance(raw, (bytes, bytearray)):
        return len(raw)
    if isinstance(raw, str):
        return len(raw.encode("utf-8"))
    # structured (e.g. table rows) — approximate by repr length; bounds runaway size.
    return len(repr(raw).encode("utf-8"))


def check_payload_size(raw: Any, max_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES) -> None:
    """Raise PayloadTooLarge if ``raw`` exceeds ``max_bytes`` (ELASTIC bound)."""
    n = _size_of(raw)
    if n > max_bytes:
        raise PayloadTooLarge(f"payload {n} bytes > bound {max_bytes}")


def guarded_extract(
    extractor: Any,
    source_doc: Document,
    raw: Any,
    audit_sink: Any | None = None,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> list[EnrichedChunk]:
    """Run ``extractor.extract`` with size + failure guards. Returns [] on a guarded
    failure (never raises into the ingest loop); the failure is AUDITED.
    """
    # ELASTIC: reject oversized payloads before touching the extractor.
    try:
        check_payload_size(raw, max_payload_bytes)
    except PayloadTooLarge as e:
        _log.warning("extraction payload too large for doc %s: %s", source_doc.doc_id, e)
        _audit(audit_sink, "payload_too_large",
               {"doc_id": source_doc.doc_id, "reason": str(e)})
        return []

    # RESILIENT: an extractor crash yields no chunks + an audited failure.
    try:
        return list(extractor.extract(source_doc, raw))
    except Exception as e:  # noqa: BLE001 - guard boundary
        _log.exception("extraction failed for doc %s", source_doc.doc_id)
        _audit(audit_sink, "extraction_failed",
               {"doc_id": source_doc.doc_id, "error": type(e).__name__})
        return []


def _audit(sink: Any | None, kind: str, detail: dict) -> None:
    if sink is None:
        return
    try:
        sink.record_event(kind, detail)
    except Exception:
        _log.exception("multimodal audit write failed (%s) — extraction continues", kind)


__all__ = ["PayloadTooLarge", "check_payload_size", "guarded_extract",
           "DEFAULT_MAX_PAYLOAD_BYTES"]

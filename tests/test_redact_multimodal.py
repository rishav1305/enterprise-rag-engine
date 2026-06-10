"""P0.10 T1 — redact_chunk WITHHOLDS non-text payloads (can't [REDACTED] a pixel).

For a mask/partial NON-TEXT chunk, redaction must remove the raw payload from
metadata (the model/citations never see raw image/table bytes) AND replace content
with a withhold token that names the modality. Text chunks are unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.governance.masking import redact_chunk  # noqa: E402
from rag_engine.multimodal.payload import attach_payload, get_payload  # noqa: E402
from rag_engine.schemas import (  # noqa: E402
    EnrichedChunk,
    GovernanceDecision,
    ScoredChunk,
    SecurityContext,
)


def _mm_chunk(modality, payload):
    md = {}
    attach_payload(md, payload)
    chunk = EnrichedChunk(
        chunk_id="c", parent_doc_id="d", parent_title="t",
        content="a caption describing the image", modality=modality, metadata=md,
        security=SecurityContext(allowed_roles=[], clearance_level=3,
                                 sensitivity_class="D", need_to_know_roles=[]),
    )
    return ScoredChunk(chunk=chunk, score=1.0)


def _mask():
    return GovernanceDecision(chunk_id="c", parent_doc_id="d", decision="mask",
                              reason="pii_masked", mask_reason="pii_mask")


def _allow():
    return GovernanceDecision(chunk_id="c", parent_doc_id="d", decision="allow",
                              reason="ok")


def test_masked_image_payload_is_withheld():
    sc = _mm_chunk("image", b"\x89PNG raw pixel bytes SECRET")
    out = redact_chunk(sc, _mask())
    # the raw payload is GONE from the redacted chunk's metadata
    assert get_payload(out.chunk.metadata) is None
    # and the content is a withhold token (no raw caption either)
    assert "[" in out.chunk.content and "image" in out.chunk.content.lower()


def test_masked_table_payload_is_withheld():
    sc = _mm_chunk("table", [["ssn", "123-45-6789"], ["name", "Bob"]])
    out = redact_chunk(sc, _mask())
    assert get_payload(out.chunk.metadata) is None
    assert "table" in out.chunk.content.lower()


def test_masked_ocr_payload_is_withheld():
    sc = _mm_chunk("ocr", b"scanned exec comp page raw")
    out = redact_chunk(sc, _mask())
    assert get_payload(out.chunk.metadata) is None


def test_masked_figure_payload_is_withheld():
    sc = _mm_chunk("figure", b"chart raster bytes SECRET")
    out = redact_chunk(sc, _mask())
    assert get_payload(out.chunk.metadata) is None
    assert "figure" in out.chunk.content.lower()


def test_masked_nontext_scrubs_bytes_in_every_location():
    """The withhold contract is 'no raw payload ANYWHERE', not 'pop one key'. Plant
    bytes under a SECOND top-level key AND inside a nested dict; after a mask, NO
    bytes value survives anywhere in the redacted metadata.

    BITES: a shallow strip of only MULTIMODAL_PAYLOAD_KEY leaves the second-location
    and nested bytes -> this fails.
    """
    chunk = EnrichedChunk(
        chunk_id="c", parent_doc_id="d", parent_title="t", content="caption",
        modality="image",
        metadata={
            "mm_payload": b"\x89PNG primary",
            "raw_bytes": b"SECOND_LOCATION_SECRET",          # a second top-level payload
            "thumb": {"bytes": b"NESTED_THUMB_SECRET"},      # nested payload
            "caption": "a safe scalar field",
        },
        security=SecurityContext(allowed_roles=[], clearance_level=3,
                                 sensitivity_class="D", need_to_know_roles=[]),
    )
    out = redact_chunk(ScoredChunk(chunk=chunk, score=1.0), _mask())

    # NO bytes value survives anywhere (recursive check).
    def _has_bytes(obj):
        if isinstance(obj, (bytes, bytearray)):
            return True
        if isinstance(obj, dict):
            return any(_has_bytes(v) for v in obj.values())
        if isinstance(obj, (list, tuple)):
            return any(_has_bytes(v) for v in obj)
        return False

    assert not _has_bytes(out.chunk.metadata), "raw bytes survived the mask"
    blob = repr(out.chunk.metadata)
    assert "SECOND_LOCATION_SECRET" not in blob
    assert "NESTED_THUMB_SECRET" not in blob


def test_redacted_metadata_shares_no_mutable_object_with_original():
    """Deep-copy: mutating the redacted chunk's nested metadata must not touch the
    original (a shallow copy would alias the nested dict)."""
    nested = {"bytes": b"x", "note": "orig"}
    chunk = EnrichedChunk(
        chunk_id="c", parent_doc_id="d", parent_title="t", content="cap",
        modality="image", metadata={"mm_payload": b"p", "thumb": nested},
        security=SecurityContext(allowed_roles=[], clearance_level=3,
                                 sensitivity_class="D", need_to_know_roles=[]),
    )
    out = redact_chunk(ScoredChunk(chunk=chunk, score=1.0), _mask())
    # if 'thumb' survives at all it must be a distinct object; and mutating the
    # original's nested dict must not leak into the redacted one.
    nested["note"] = "MUTATED_AFTER_REDACT"
    assert "MUTATED_AFTER_REDACT" not in repr(out.chunk.metadata)


def test_allow_passes_payload_through_unchanged():
    sc = _mm_chunk("image", b"public chart bytes")
    out = redact_chunk(sc, _allow())
    # allow -> the chunk (and its payload) passes through unchanged
    assert get_payload(out.chunk.metadata) == b"public chart bytes"


def test_text_chunk_redaction_unchanged_regression():
    chunk = EnrichedChunk(chunk_id="c", parent_doc_id="d", parent_title="t",
                          content="raw secret text", modality="text",
                          security=SecurityContext(allowed_roles=[], clearance_level=3,
                                                   sensitivity_class="D",
                                                   need_to_know_roles=[]))
    out = redact_chunk(ScoredChunk(chunk=chunk, score=1.0), _mask())
    assert out.chunk.content == "[REDACTED]"   # text masking unchanged

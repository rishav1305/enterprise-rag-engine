"""WORKER-A — the multimodal leak oracle: non-text is governed identically to text.

Through the REAL SecurityFilter.apply for an under-cleared session:
  * a MASKED image/table/OCR chunk is WITHHELD — content is a withhold token AND the
    raw payload is gone from metadata (the model/citations never see raw bytes),
    across all three modalities;
  * a DENIED non-text chunk is excluded from the allowlist (same pre-filter as text).

MUTATION (the bite, Friday also runs): skip the non-text payload-strip in redaction
-> the raw image/table payload surfaces in the admitted chunk's metadata -> fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.governance.allowlist import authorized_chunk_ids  # noqa: E402
from rag_engine.governance.filter import SecurityFilter  # noqa: E402
from rag_engine.multimodal.payload import attach_payload, get_payload  # noqa: E402
from rag_engine.schemas import (  # noqa: E402
    EnrichedChunk,
    ScoredChunk,
    SecurityContext,
    Session,
)

SECRET_BYTES = b"RAW_PIXEL_SECRET_4POINT2M"


def _mm(chunk_id, modality, cls, level, ntk, payload):
    md = {}
    attach_payload(md, payload)
    return EnrichedChunk(
        chunk_id=chunk_id, parent_doc_id="d", parent_title="t",
        content=f"{modality} caption", modality=modality, metadata=md,
        security=SecurityContext(allowed_roles=ntk, clearance_level=level,
                                 sensitivity_class=cls, need_to_know_roles=ntk),
    )


def _under_cleared():
    return Session(user_id="emp", roles=["EMPLOYEE"], clearance_level=2)


def test_masked_nontext_is_withheld_across_modalities():
    # class-D (PII) chunks at clearance 1 -> MASK for an L2 session (admitted-but-
    # withheld). One per modality, each carrying a raw payload.
    chunks = [
        ScoredChunk(chunk=_mm("img:1", "image", "D", 1, [], SECRET_BYTES), score=1.0),
        ScoredChunk(chunk=_mm("tbl:1", "table", "D", 1, [],
                              [["ssn", "123-45-6789"]]), score=1.0),
        ScoredChunk(chunk=_mm("ocr:1", "ocr", "D", 1, [], b"scanned raw"), score=1.0),
        ScoredChunk(chunk=_mm("fig:1", "figure", "D", 1, [], SECRET_BYTES), score=1.0),
    ]
    admitted, trail = SecurityFilter().apply(chunks, _under_cleared())

    assert {d.decision for d in trail} == {"mask"}        # all masked, not denied
    assert len(admitted) == 4                              # admitted-but-withheld (4 modalities)
    for sc in admitted:
        # the raw payload is GONE (withheld) for every modality
        assert get_payload(sc.chunk.metadata) is None, \
            f"MULTIMODAL LEAK: raw {sc.chunk.modality} payload survived the mask"
        # content is a withhold token, never the raw caption
        assert "withheld" in sc.chunk.content.lower()


def test_denied_nontext_excluded_from_allowlist():
    # a class-F (exec-comp, NTK C_SUITE, level 5) IMAGE -> DENY for the under-cleared
    # session: never on the allowlist (same pre-filter as text).
    img = _mm("img:secret", "image", "F", 5, ["C_SUITE"], SECRET_BYTES)
    pub = _mm("img:pub", "image", "B", 1, [], b"public chart")
    allow = set(authorized_chunk_ids(_under_cleared(), [img, pub]))
    assert "img:secret" not in allow          # denied image pre-filtered out
    assert "img:pub" in allow                 # public image retrievable


def test_no_raw_bytes_anywhere_in_admitted_provenance():
    # belt-and-suspenders: the secret bytes appear NOWHERE in the admitted set.
    chunks = [ScoredChunk(chunk=_mm("img:1", "image", "D", 1, [], SECRET_BYTES),
                          score=1.0)]
    admitted, _ = SecurityFilter().apply(chunks, _under_cleared())
    blob = repr([(sc.chunk.content, sc.chunk.metadata) for sc in admitted])
    assert "RAW_PIXEL_SECRET" not in blob

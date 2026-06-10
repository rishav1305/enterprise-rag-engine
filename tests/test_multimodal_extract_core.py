"""P0.10 T2 — modality extractors INHERIT the source doc's classification.

Every chunk an extractor produces carries the SOURCE document's SecurityContext —
text OCR'd from a class-F scanned PDF is class-F, never a fresh/public default
(no declassification-by-extraction). And each tags its modality.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.multimodal.extract import (  # noqa: E402
    FakeImageExtractor,
    FakeOcrExtractor,
    FakeTableExtractor,
    ModalityExtractor,
)
from rag_engine.multimodal.payload import get_payload  # noqa: E402
from rag_engine.schemas import Document, SecurityContext  # noqa: E402


def _restricted_doc():
    # a class-F (exec-comp) scanned source — its extracted chunks must inherit this.
    return Document(
        doc_id="scan-1", title="Exec Comp Scan", content="(binary source)",
        security=SecurityContext(allowed_roles=["C_SUITE"], clearance_level=5,
                                 sensitivity_class="F", need_to_know_roles=["C_SUITE"]),
    )


def test_extractors_satisfy_protocol():
    for ex in (FakeImageExtractor(), FakeTableExtractor(), FakeOcrExtractor()):
        assert isinstance(ex, ModalityExtractor)


def test_ocr_chunks_inherit_source_classification():
    doc = _restricted_doc()
    chunks = FakeOcrExtractor().extract(doc, raw=b"scanned page bytes")
    assert chunks
    for c in chunks:
        # SecurityContext is the SOURCE's, byte-identical — NOT a fresh public one.
        assert c.security.sensitivity_class == "F"
        assert c.security.clearance_level == 5
        assert c.security.need_to_know_roles == ["C_SUITE"]
        assert c.modality == "ocr"


def test_image_extractor_tags_modality_and_inherits():
    doc = _restricted_doc()
    chunks = FakeImageExtractor().extract(doc, raw=b"\x89PNG bytes")
    assert all(c.modality == "image" for c in chunks)
    assert all(c.security.sensitivity_class == "F" for c in chunks)
    # the image payload rides along in metadata
    assert any(get_payload(c.metadata) is not None for c in chunks)


def test_table_extractor_tags_modality_and_inherits():
    doc = _restricted_doc()
    chunks = FakeTableExtractor().extract(doc, raw=[["a", "1"], ["b", "2"]])
    assert all(c.modality == "table" for c in chunks)
    assert all(c.security.sensitivity_class == "F" for c in chunks)


def test_public_doc_extracts_public_chunks():
    # sanity: a genuinely public source yields public chunks (inheritance is faithful
    # both ways, not a hardcoded restriction).
    pub = Document(doc_id="d", title="t", content="x",
                   security=SecurityContext(allowed_roles=["PUBLIC"], clearance_level=0,
                                            sensitivity_class="A", need_to_know_roles=[]))
    chunks = FakeOcrExtractor().extract(pub, raw=b"public scan")
    assert all(c.security.sensitivity_class == "A" for c in chunks)

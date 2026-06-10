"""P0.11a W6 — multimodal guarded_extract wired into ingest.

index_multimodal runs an extractor under guarded_extract; produced chunks inherit
the source doc's SecurityContext and are governed identically to text at query time.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.multimodal.extract import FakeImageExtractor, FakeOcrExtractor  # noqa: E402
from rag_engine.multimodal.payload import get_payload  # noqa: E402
from rag_engine.pipeline import RAGPipeline  # noqa: E402
from rag_engine.schemas import Document, SecurityContext, Session  # noqa: E402

SECRET = "MM_INGEST_EXEC_SECRET"


def _restricted_doc():
    return Document(doc_id="scan1", title="Exec Comp Scan",
                    content=f"(binary) {SECRET}",
                    security=SecurityContext(allowed_roles=["C_SUITE"], clearance_level=5,
                                             sensitivity_class="F",
                                             need_to_know_roles=["C_SUITE"]))


def test_index_multimodal_adds_inherited_chunks():
    pipe = RAGPipeline()
    n = pipe.index_multimodal(_restricted_doc(), raw=b"scanned page", extractor=FakeOcrExtractor())
    assert n == 1
    mm = [c for c in pipe._chunks if c.modality == "ocr"]
    assert mm and mm[0].security.sensitivity_class == "F"   # inherited, not public


def test_ingested_image_governed_identically_at_query():
    pipe = RAGPipeline()
    pipe.index_multimodal(_restricted_doc(), raw=b"\x89PNG raw", extractor=FakeImageExtractor())
    # an under-cleared session querying must NOT get the restricted image's content;
    # the F-class image chunk is DENIED -> dropped before the model (same L5 path).
    intern = Session(user_id="intern", roles=["INTERN"], clearance_level=1)
    resp = pipe.query("exec comp scan", intern)
    assert SECRET not in resp.answer


def test_oversized_payload_rejected_and_audited():
    from rag_engine.governance.audit_sink import InMemoryAuditSink
    pipe = RAGPipeline()
    pipe.audit_sink = InMemoryAuditSink()
    # a payload over the bound -> guarded_extract rejects it + audits (no chunks added)
    n = pipe.index_multimodal(_restricted_doc(), raw=b"x" * (30 * 1024 * 1024),
                              extractor=FakeOcrExtractor())
    # default bound is 25 MiB -> rejected
    assert n == 0
    assert len(pipe.audit_sink.by_kind("payload_too_large")) == 1


def test_masked_image_payload_withheld_end_to_end():
    # a class-D (PII) image -> MASK for an L2 session: admitted-but-withheld (no raw
    # payload reaches the model). Asserts the raw payload is gone from the admitted set.
    pipe = RAGPipeline()
    doc = Document(doc_id="pii_scan", title="Customer Scan", content="(binary)",
                   security=SecurityContext(allowed_roles=[], clearance_level=1,
                                            sensitivity_class="D", need_to_know_roles=[]))
    pipe.index_multimodal(doc, raw=b"RAW_PII_IMAGE_BYTES", extractor=FakeImageExtractor())
    img = [c for c in pipe._chunks if c.modality == "image"][0]
    from rag_engine.schemas import ScoredChunk
    admitted, _ = pipe.security.apply(
        [ScoredChunk(chunk=img, score=1.0)],
        Session(user_id="emp", roles=["EMPLOYEE"], clearance_level=2))
    assert admitted   # mask -> admitted-but-withheld
    assert get_payload(admitted[0].chunk.metadata) is None   # raw payload withheld

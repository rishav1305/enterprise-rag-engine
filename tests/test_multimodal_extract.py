"""WORKER-B — extraction inherits classification: no declassify-by-extraction.

OCR'd / extracted chunks from a restricted source are governed by the SOURCE's
classification end-to-end (denied/masked for an under-cleared session), NOT treated
as fresh public text.

MUTATION (the bite): an extractor that mints a fresh/default (public) SecurityContext
-> the under-cleared session can now retrieve the extracted restricted content -> fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.governance import access  # noqa: E402
from rag_engine.governance.allowlist import authorized_chunk_ids  # noqa: E402
from rag_engine.multimodal.extract import (  # noqa: E402
    FakeImageExtractor,
    FakeOcrExtractor,
    FakeTableExtractor,
)
from rag_engine.schemas import Document, SecurityContext, Session  # noqa: E402


def _restricted_doc():
    return Document(
        doc_id="scan-1", title="Exec Comp Scan", content="(binary)",
        security=SecurityContext(allowed_roles=["C_SUITE"], clearance_level=5,
                                 sensitivity_class="F", need_to_know_roles=["C_SUITE"]),
    )


def _under_cleared():
    return Session(user_id="emp", roles=["EMPLOYEE"], clearance_level=2)


def test_ocr_of_restricted_pdf_is_denied_to_under_cleared():
    chunks = FakeOcrExtractor().extract(_restricted_doc(), raw=b"scanned page")
    # the OCR chunk is class-F -> DENY for the under-cleared session (governance the
    # SAME as if a human had typed the restricted text).
    for c in chunks:
        assert access.evaluate(c, _under_cleared()).decision == "deny"
    allow = set(authorized_chunk_ids(_under_cleared(), chunks))
    assert allow == set()    # nothing extracted from the restricted scan is retrievable


def test_restricted_image_and_table_also_denied():
    doc = _restricted_doc()
    img = FakeImageExtractor().extract(doc, raw=b"\x89PNG")
    tbl = FakeTableExtractor().extract(doc, raw=[["x", "1"]])
    for c in img + tbl:
        assert access.evaluate(c, _under_cleared()).decision == "deny"


def test_cleared_session_can_see_extracted_restricted():
    # sanity: a CLEARED session legitimately retrieves the extracted restricted chunks
    cfo = Session(user_id="cfo", roles=["C_SUITE"], clearance_level=5)
    chunks = FakeOcrExtractor().extract(_restricted_doc(), raw=b"scan")
    allow = set(authorized_chunk_ids(cfo, chunks))
    assert allow == {c.chunk_id for c in chunks}   # all retrievable for the C_SUITE


def test_public_extraction_stays_public():
    pub = Document(doc_id="d", title="t", content="x",
                   security=SecurityContext(allowed_roles=["PUBLIC"], clearance_level=0,
                                            sensitivity_class="A", need_to_know_roles=[]))
    chunks = FakeOcrExtractor().extract(pub, raw=b"public")
    # a public source's extraction is retrievable by anyone (inheritance is faithful
    # both directions — not a blanket restriction).
    allow = set(authorized_chunk_ids(_under_cleared(), chunks))
    assert allow == {c.chunk_id for c in chunks}

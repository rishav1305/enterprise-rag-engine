"""WORKER-D — multimodal robustness + TRANSPARENT: audited failures, bounded payloads.

An extraction failure is AUDITED (bounded, not silent); a payload over a configured
size bound is rejected (ELASTIC — bounded binary footprint); modality is recorded so
it's observable.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rag_engine.governance.audit_sink import InMemoryAuditSink  # noqa: E402
from rag_engine.multimodal.extract import FakeOcrExtractor  # noqa: E402
from rag_engine.multimodal.robust import (  # noqa: E402
    PayloadTooLarge,
    guarded_extract,
    check_payload_size,
)
from rag_engine.schemas import Document, SecurityContext  # noqa: E402


def _doc():
    return Document(doc_id="d", title="t", content="x",
                    security=SecurityContext(allowed_roles=[], clearance_level=1,
                                             sensitivity_class="B", need_to_know_roles=[]))


class _BoomExtractor:
    def extract(self, source_doc, raw):
        raise RuntimeError("OCR engine crashed")


def test_guarded_extract_audits_failure_not_silent():
    audit = InMemoryAuditSink()
    chunks = guarded_extract(_BoomExtractor(), _doc(), raw=b"x", audit_sink=audit)
    assert chunks == []                              # failure -> no chunks (not a crash)
    recs = audit.by_kind("extraction_failed")
    assert len(recs) == 1                            # the failure is AUDITED
    assert recs[0]["detail"]["doc_id"] == "d"


def test_guarded_extract_passes_through_on_success():
    audit = InMemoryAuditSink()
    chunks = guarded_extract(FakeOcrExtractor(), _doc(), raw=b"scan", audit_sink=audit)
    assert len(chunks) == 1 and chunks[0].modality == "ocr"
    assert audit.by_kind("extraction_failed") == []  # no failure audited


def test_payload_over_bound_rejected():
    with pytest.raises(PayloadTooLarge):
        check_payload_size(b"x" * 1000, max_bytes=100)


def test_payload_within_bound_ok():
    check_payload_size(b"x" * 50, max_bytes=100)     # no raise


def test_guarded_extract_rejects_oversized_payload():
    audit = InMemoryAuditSink()
    chunks = guarded_extract(FakeOcrExtractor(), _doc(), raw=b"x" * 1000,
                             audit_sink=audit, max_payload_bytes=100)
    assert chunks == []                              # oversized -> rejected
    assert len(audit.by_kind("payload_too_large")) == 1

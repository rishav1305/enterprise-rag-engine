"""P0.2c HEADLINE — E2E C1-over-vector through the LIVE TurboVec path.

The deferred governance proof: a class-D chunk with raw PII, retrieved through the
LIVE TurboVec retriever path (allowlist pre-filter at the index + mandatory rerank
+ L5 C1 masking), is `[REDACTED]` in BOTH the answer and the citations, with raw
PII (email/phone/SSN) never present — and a class-F (L5) chunk in the same index
is never retrieved at all for an L2 analyst (allowlist pre-filter, live).

This turns the P0.2b "built, not wired" pieces into LIVE-ENFORCED governance.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

pytest.importorskip("turbovec")

from rag_engine import RAGPipeline, Session  # noqa: E402
from rag_engine.config import EngineConfig  # noqa: E402
from rag_engine.retrieval.embedders import HashingEmbedder  # noqa: E402
from rag_engine.retrieval.rerank import LexicalOverlapReranker  # noqa: E402
from rag_engine.retrieval.turbovec_index import TurboVecIndex  # noqa: E402
from rag_engine.retrieval.turbovec_retriever import TurboVecRetriever  # noqa: E402
from rag_engine.schemas import EnrichedChunk, SecurityContext  # noqa: E402

_RAW_PII = "Customer jane.doe@example.com phone 555-867-5309 SSN 123-45-6789 contact record"
_SECRETS = ("jane.doe@example.com", "555-867-5309", "123-45-6789")


class _DictSource:
    def __init__(self, chunks):
        self._by_id = {c.chunk_id: c for c in chunks}

    def get_chunk(self, chunk_id):
        return self._by_id.get(chunk_id)

    def all_chunk_security(self):
        return list(self._by_id.values())


def _chunk(cid, content, cls, level, ntk):
    return EnrichedChunk(
        chunk_id=cid, parent_doc_id=cid, parent_title="Record", content=content,
        security=SecurityContext(allowed_roles=ntk, clearance_level=level,
                                 sensitivity_class=cls, need_to_know_roles=ntk),
    )


@pytest.fixture
def vector_pipeline_with_pii():
    cfg = EngineConfig()
    emb = HashingEmbedder(dim=cfg.embedding_dim)
    chunks = [
        _chunk("chunk:cust", _RAW_PII, "D", 3, []),                 # customer PII (mask leg)
        _chunk("chunk:execcomp", "exec comp ceo salary 480000 contact", "F", 5, ["C_SUITE"]),
        _chunk("chunk:pub", "remote work stipend 500 dollars contact", "B", 1, []),
    ]
    source = _DictSource(chunks)
    vecs = emb.embed([c.embedding_text for c in chunks]).astype("float32")
    idx = TurboVecIndex(dim=cfg.embedding_dim)
    idx.add([c.chunk_id for c in chunks], vecs)
    retriever = TurboVecRetriever(idx, emb, source, LexicalOverlapReranker(), cfg)
    pipe = RAGPipeline(config=cfg, vector_retriever=retriever)
    analyst = Session(user_id="ma", roles=["MARKETING_ANALYST", "EMPLOYEE"], clearance_level=2)
    return pipe, analyst


def test_class_D_pii_redacted_via_live_turbovec_path(vector_pipeline_with_pii):
    pipe, analyst = vector_pipeline_with_pii
    resp = pipe.query("show me the customer contact record", analyst)
    # raw PII must appear NOWHERE in the answer or citations
    for secret in _SECRETS:
        assert secret not in resp.answer, f"LEAK in answer: {secret}"
        for c in resp.citations:
            assert secret not in c.quote, f"LEAK in citation: {secret}"


def test_class_D_chunk_is_masked_not_dropped(vector_pipeline_with_pii):
    pipe, analyst = vector_pipeline_with_pii
    resp = pipe.query("customer contact record", analyst)
    # the masked chunk is still retrievable (mask, not blackout) -> redaction token
    quotes = " ".join(c.quote for c in resp.citations)
    assert "[REDACTED]" in quotes or "[RESTRICTED]" in quotes


def test_class_F_L5_chunk_never_retrieved_for_analyst(vector_pipeline_with_pii):
    pipe, analyst = vector_pipeline_with_pii
    resp = pipe.query("exec comp ceo salary contact", analyst)
    # the L5 exec-comp chunk is excluded at the index (allowlist pre-filter, live)
    assert "chunk:execcomp" not in {c.parent_doc_id for c in resp.citations}
    assert "480000" not in resp.answer


def test_cfo_does_get_exec_comp_via_live_path(vector_pipeline_with_pii):
    # negative control: with the right token, the same index returns the L5 chunk
    pipe, _ = vector_pipeline_with_pii
    cfo = Session(user_id="cfo", roles=["C_SUITE", "FINANCE", "EMPLOYEE"], clearance_level=5)
    resp = pipe.query("exec comp ceo salary contact", cfo)
    assert "chunk:execcomp" in {c.parent_doc_id for c in resp.citations}

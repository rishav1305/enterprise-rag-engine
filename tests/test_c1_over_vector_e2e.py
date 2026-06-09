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
    # expose the retriever so the E2E can assert on the CANDIDATE SET (pre-post-filter)
    return pipe, analyst, retriever


def test_class_D_pii_redacted_via_live_turbovec_path(vector_pipeline_with_pii):
    pipe, analyst, _ = vector_pipeline_with_pii
    resp = pipe.query("show me the customer contact record", analyst)
    # raw PII must appear NOWHERE in the answer or citations
    for secret in _SECRETS:
        assert secret not in resp.answer, f"LEAK in answer: {secret}"
        for c in resp.citations:
            assert secret not in c.quote, f"LEAK in citation: {secret}"


def test_class_D_chunk_is_masked_not_dropped(vector_pipeline_with_pii):
    pipe, analyst, _ = vector_pipeline_with_pii
    resp = pipe.query("customer contact record", analyst)
    # the masked chunk is still retrievable (mask, not blackout) -> redaction token
    quotes = " ".join(c.quote for c in resp.citations)
    assert "[REDACTED]" in quotes or "[RESTRICTED]" in quotes


def test_class_F_L5_chunk_excluded_at_index_before_post_filter(vector_pipeline_with_pii):
    """HARDENED: assert the L5 chunk never enters the CANDIDATE SET for the analyst
    — i.e. it was dropped by the allowlist PRE-filter (drop-before-search), not
    merely masked by the L5 post-filter. This test FAILS if the pre-filter is
    bypassed (allowlist disabled), independent of the post-filter."""
    pipe, analyst, retriever = vector_pipeline_with_pii
    # candidate set straight from the retriever (BEFORE the L5 SecurityFilter runs)
    candidates = retriever.retrieve_for_session("exec comp ceo salary contact", analyst)
    candidate_ids = {sc.chunk.chunk_id for sc in candidates}
    assert "chunk:execcomp" not in candidate_ids, (
        "PRE-FILTER BYPASS: the L5 chunk reached the candidate set — the allowlist "
        "drop-before-search is not enforcing (post-filter would mask, hiding this)."
    )
    # and end-to-end the secret never surfaces
    resp = pipe.query("exec comp ceo salary contact", analyst)
    assert "chunk:execcomp" not in {c.parent_doc_id for c in resp.citations}
    assert "480000" not in resp.answer


def test_cfo_does_get_exec_comp_via_live_path(vector_pipeline_with_pii):
    # negative control: with the right token, the same index returns the L5 chunk
    pipe, _, retriever = vector_pipeline_with_pii
    cfo = Session(user_id="cfo", roles=["C_SUITE", "FINANCE", "EMPLOYEE"], clearance_level=5)
    # the L5 chunk IS in the CFO's candidate set (pre-filter admits it)
    candidate_ids = {sc.chunk.chunk_id
                     for sc in retriever.retrieve_for_session("exec comp ceo salary contact", cfo)}
    assert "chunk:execcomp" in candidate_ids
    resp = pipe.query("exec comp ceo salary contact", cfo)
    assert "chunk:execcomp" in {c.parent_doc_id for c in resp.citations}


# ---- edge cases (test-coverage hardening) ------------------------------
def test_hydrate_of_missing_id_is_dropped_no_raise():
    """Store drift: an id in the index/allowlist whose get_chunk returns None ->
    the retriever drops it and returns the rest, no raise / None-deref."""
    cfg = EngineConfig()
    emb = HashingEmbedder(dim=cfg.embedding_dim)
    present = _chunk("chunk:here", "stipend 500 contact", "B", 1, [])
    ghost = _chunk("chunk:ghost", "ghost record contact", "B", 1, [])
    # source knows BOTH for the allowlist, but get_chunk returns None for the ghost
    class _DriftSource:
        def get_chunk(self, cid):
            return present if cid == "chunk:here" else None
        def all_chunk_security(self):
            return [present, ghost]
    vecs = emb.embed([present.embedding_text, ghost.embedding_text]).astype("float32")
    idx = TurboVecIndex(dim=cfg.embedding_dim)
    idx.add(["chunk:here", "chunk:ghost"], vecs)
    r = TurboVecRetriever(idx, emb, _DriftSource(), LexicalOverlapReranker(), cfg)
    emp = Session(user_id="e", roles=["EMPLOYEE"], clearance_level=1)
    hits = r.retrieve_for_session("contact", emp)
    ids = {h.chunk.chunk_id for h in hits}
    assert "chunk:ghost" not in ids       # missing id dropped
    assert "chunk:here" in ids            # the rest still returned


def test_reranker_over_empty_candidate_set_returns_empty():
    cfg = EngineConfig()
    emb = HashingEmbedder(dim=cfg.embedding_dim)
    only = _chunk("chunk:x", "exec comp", "F", 5, ["C_SUITE"])  # L5

    class _Src:
        def get_chunk(self, cid):
            return only if cid == "chunk:x" else None
        def all_chunk_security(self):
            return [only]
    idx = TurboVecIndex(dim=cfg.embedding_dim)
    idx.add(["chunk:x"], emb.embed([only.embedding_text]).astype("float32"))
    r = TurboVecRetriever(idx, emb, _Src(), LexicalOverlapReranker(), cfg)
    intern = Session(user_id="i", roles=["INTERN", "EMPLOYEE"], clearance_level=1)
    # intern is cleared for nothing here -> empty allowlist -> empty candidates -> []
    assert r.retrieve_for_session("exec comp", intern) == []


def test_coarse_k_larger_than_corpus_returns_all_no_error():
    cfg = EngineConfig()
    object.__setattr__(cfg, "vector_coarse_k", 10_000)  # >> corpus
    emb = HashingEmbedder(dim=cfg.embedding_dim)
    chunks = [_chunk(f"chunk:{i}", f"public record {i} contact", "B", 1, []) for i in range(5)]

    class _Src:
        def __init__(s):
            s.d = {c.chunk_id: c for c in chunks}
        def get_chunk(s, cid):
            return s.d.get(cid)
        def all_chunk_security(s):
            return list(s.d.values())
    idx = TurboVecIndex(dim=cfg.embedding_dim)
    idx.add([c.chunk_id for c in chunks], emb.embed([c.embedding_text for c in chunks]).astype("float32"))
    r = TurboVecRetriever(idx, emb, _Src(), LexicalOverlapReranker(), cfg)
    emp = Session(user_id="e", roles=["EMPLOYEE"], clearance_level=1)
    hits = r.retrieve_for_session("contact", emp)
    assert len(hits) <= cfg.final_top_k  # no error; rerank caps to final_top_k


def test_multi_class_mixed_response_B_raw_D_masked_F_dropped(vector_pipeline_with_pii):
    """One query, one response, three behaviors: B raw, D masked, F dropped."""
    pipe, analyst, _ = vector_pipeline_with_pii
    resp = pipe.query("customer contact record stipend exec comp", analyst)
    cited = {c.parent_doc_id for c in resp.citations}
    quotes = " ".join(c.quote for c in resp.citations)
    # B: public chunk admitted raw (its content survives)
    assert "chunk:pub" in cited
    assert "500" in quotes or "stipend" in quotes.lower()
    # D: customer-PII admitted but MASKED (redaction token, raw PII absent)
    assert "chunk:cust" in cited
    assert "[REDACTED]" in quotes
    for secret in _SECRETS:
        assert secret not in quotes and secret not in resp.answer
    # F: exec-comp (L5) DROPPED — never cited, secret absent
    assert "chunk:execcomp" not in cited
    assert "480000" not in resp.answer

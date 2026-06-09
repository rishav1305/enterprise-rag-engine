"""P0.2c — TurboVecRetriever unit tests (allowlist pre-filter + mandatory rerank)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

pytest.importorskip("turbovec")

from rag_engine.config import EngineConfig  # noqa: E402
from rag_engine.retrieval.embedders import HashingEmbedder  # noqa: E402
from rag_engine.retrieval.turbovec_index import TurboVecIndex  # noqa: E402
from rag_engine.schemas import EnrichedChunk, SecurityContext, Session  # noqa: E402


class _DictSource:
    """In-memory ChunkSource for unit tests (mirrors the SurrealDB store contract)."""

    def __init__(self, chunks: list[EnrichedChunk]) -> None:
        self._by_id = {c.chunk_id: c for c in chunks}

    def get_chunk(self, chunk_id: str) -> EnrichedChunk | None:
        return self._by_id.get(chunk_id)

    def all_chunk_security(self) -> list[EnrichedChunk]:
        return list(self._by_id.values())


def _chunk(cid, content, cls, level, ntk):
    return EnrichedChunk(
        chunk_id=cid, parent_doc_id=cid, parent_title="t", content=content,
        security=SecurityContext(allowed_roles=ntk, clearance_level=level,
                                 sensitivity_class=cls, need_to_know_roles=ntk),
    )


@pytest.fixture
def tiny_setup():
    cfg = EngineConfig()
    emb = HashingEmbedder(dim=cfg.embedding_dim)
    # 1 public + 1 class-F (L5) "secret" chunk + a few fillers
    chunks = [
        _chunk("chunk:pub", "remote work stipend is 500 dollars", "B", 1, []),
        _chunk("chunk:secret", "exec comp ceo salary 480000", "F", 5, ["C_SUITE"]),
        _chunk("chunk:ops", "average trip fare by borough", "C", 2, []),
        _chunk("chunk:cust", "customer email contact jane example com", "D", 3, []),
    ]
    source = _DictSource(chunks)
    texts = [c.embedding_text for c in chunks]
    vecs = emb.embed(texts).astype("float32")
    idx = TurboVecIndex(dim=cfg.embedding_dim)
    idx.add([c.chunk_id for c in chunks], vecs)
    from rag_engine.retrieval.rerank import LexicalOverlapReranker
    return idx, emb, source, LexicalOverlapReranker(), cfg


def test_retriever_excludes_unauthorized_and_reranks(tiny_setup):
    idx, emb, source, reranker, cfg = tiny_setup
    from rag_engine.retrieval.turbovec_retriever import TurboVecRetriever
    r = TurboVecRetriever(idx, emb, source, reranker, cfg)
    intern = Session(user_id="i", roles=["INTERN", "EMPLOYEE"], clearance_level=1)
    hits = r.retrieve_for_session("customer email", intern)
    ids = {h.chunk.chunk_id for h in hits}
    assert "chunk:secret" not in ids        # L5 (class F) excluded at the index
    assert all(h.chunk.content for h in hits)  # store-hydrated, not bare ids


def test_retriever_reranks_always_even_if_config_says_false(tiny_setup):
    idx, emb, source, reranker, cfg = tiny_setup
    # attempt to disable rerank on the vector path — retriever must ignore it
    object.__setattr__(cfg, "vector_path_rerank_mandatory", False) if hasattr(
        cfg, "vector_path_rerank_mandatory") else None
    from rag_engine.retrieval.turbovec_index import TurboVecIndex as _T  # noqa: F401
    from rag_engine.retrieval.turbovec_retriever import TurboVecRetriever

    class _CountingReranker:
        calls = 0
        def rerank(self, query, candidates, top_k):
            _CountingReranker.calls += 1
            return candidates[:top_k]

    rr = _CountingReranker()
    r = TurboVecRetriever(idx, emb, source, rr, cfg)
    cfo = Session(user_id="c", roles=["C_SUITE", "FINANCE", "EMPLOYEE"], clearance_level=5)
    r.retrieve_for_session("exec comp", cfo)
    assert rr.calls == 1  # rerank ran on the vector path regardless


def test_retriever_returns_at_most_final_top_k(tiny_setup):
    idx, emb, source, reranker, cfg = tiny_setup
    from rag_engine.retrieval.turbovec_retriever import TurboVecRetriever
    r = TurboVecRetriever(idx, emb, source, reranker, cfg)
    cfo = Session(user_id="c", roles=["C_SUITE", "FINANCE", "EMPLOYEE"], clearance_level=5)
    hits = r.retrieve_for_session("anything", cfo)
    assert len(hits) <= cfg.final_top_k


def test_empty_allowlist_returns_nothing(tiny_setup):
    # a session cleared for NOTHING gets an empty result (fail-closed)
    idx, emb, source, reranker, cfg = tiny_setup
    from rag_engine.retrieval.turbovec_retriever import TurboVecRetriever

    class _NoneAllowed:
        def get_chunk(self, cid):
            return None
        def all_chunk_security(self):
            # one chunk requiring a role nobody in this session holds, L5
            return [_chunk("chunk:x", "x", "F", 5, ["C_SUITE"])]

    r = TurboVecRetriever(idx, emb, _NoneAllowed(), reranker, cfg)
    intern = Session(user_id="i", roles=["INTERN", "EMPLOYEE"], clearance_level=1)
    assert r.retrieve_for_session("anything", intern) == []


def test_config_vector_path_rerank_is_mandatory():
    cfg = EngineConfig()
    assert cfg.vector_coarse_k >= cfg.final_top_k     # over-fetch for the reranker
    assert cfg.vector_path_rerank_mandatory is True   # load-bearing; not disableable

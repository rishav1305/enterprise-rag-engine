"""TurboVecRetriever — the LIVE session-aware vector retrieval path (P0.2c).

Turns the P0.2b "built, not wired" pieces into enforcement:

  1. derive the per-session ALLOWLIST (chunk ids the session may retrieve) from the
     governance layer over the chunk source's ACLs;
  2. embed the query and run ``TurboVecIndex.search(..., allowlist_chunk_ids=allow)``
     — unauthorized vectors are never candidates (permission PRE-filter at the index);
  3. HYDRATE the returned ids to full chunks (text + ACLs) from the source
     (SurrealDB store in production; an in-memory source in tests);
  4. **always RERANK** the coarse set — the reranker is load-bearing on the vector
     path (P0.2b finding: ~0.45 coarse recall on tight clusters; rerank recovers to
     ~0.80+). This is NON-DISABLEABLE here regardless of config;
  5. return ``ScoredChunk``s to the pipeline, where the L5 ``SecurityFilter`` (C1
     masking) runs as the second gate (defense in depth: pre-filter drops *denied*,
     post-filter *masks* mask/partial).
"""

from __future__ import annotations

from typing import Protocol

from ..config import EngineConfig
from ..governance.allowlist import authorized_chunk_ids
from ..schemas import EnrichedChunk, ScoredChunk, Session
from .base import Embedder, Reranker
from .turbovec_index import TurboVecIndex


class ChunkSource(Protocol):
    """Source of chunk text + ACLs by id (SurrealDB store or in-memory)."""

    def get_chunk(self, chunk_id: str) -> EnrichedChunk | None: ...
    def all_chunk_security(self) -> list[EnrichedChunk]: ...


class TurboVecRetriever:
    def __init__(
        self,
        index: TurboVecIndex,
        embedder: Embedder,
        source: ChunkSource,
        reranker: Reranker,
        config: EngineConfig | None = None,
    ) -> None:
        self.index = index
        self.embedder = embedder
        self.source = source
        self.reranker = reranker
        self.config = config or EngineConfig()

    def retrieve_for_session(self, query: str, session: Session) -> list[ScoredChunk]:
        cfg = self.config
        # 1) per-session allowlist from governance (decision != deny)
        allow = authorized_chunk_ids(session, self.source.all_chunk_security())
        if not allow:
            return []  # nothing the session may see (fail-closed)

        # 2) coarse ANN search with the allowlist PRE-filter at the index
        q_vec = self.embedder.embed([query])[0]
        coarse = self.index.search(q_vec, cfg.vector_coarse_k, allowlist_chunk_ids=allow)

        # 3) hydrate ids -> full chunks (text + ACLs) from the source
        candidates: list[ScoredChunk] = []
        for hit in coarse:
            chunk = self.source.get_chunk(hit.chunk_id)
            if chunk is not None:
                candidates.append(ScoredChunk(chunk=chunk, score=hit.score))

        # 4) MANDATORY rerank on the vector path — load-bearing, not config-gated.
        #    (cfg.vector_path_rerank_mandatory documents the invariant; we always
        #    rerank here regardless of its value.)
        return self.reranker.rerank(query, candidates, cfg.final_top_k)

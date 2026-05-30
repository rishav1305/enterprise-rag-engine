"""The dual-engine hybrid retriever.

Lexical (BM25) and dense (vector) run independently over the same anchored
corpus, their ranked lists are merged with Reciprocal Rank Fusion, and the top
fused candidates go through a reranker before reaching governance.

Crucially, retrieval is **permission-blind**: it finds the best content
regardless of who is asking. Enforcement happens *after*, in Layer 5. That
separation is deliberate — it lets the adversarial test prove that restricted
data was genuinely findable and was blocked by policy, not merely missed.
"""

from __future__ import annotations

import numpy as np

from ..config import EngineConfig
from ..schemas import EnrichedChunk, ScoredChunk
from .base import Embedder, Reranker, VectorStore
from .embedders import HashingEmbedder
from .fusion import reciprocal_rank_fusion
from .lexical import BM25Index
from .rerank import LexicalOverlapReranker
from .vector_store import InMemoryVectorStore


class HybridRetriever:
    def __init__(
        self,
        config: EngineConfig | None = None,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.config = config or EngineConfig()
        self.embedder = embedder or HashingEmbedder(dim=self.config.embedding_dim)
        self.vector_store = vector_store or InMemoryVectorStore()
        self.lexical = BM25Index()
        self.reranker = reranker or LexicalOverlapReranker()
        self._indexed = False

    def index(self, chunks: list[EnrichedChunk]) -> None:
        vectors = self.embedder.embed([c.embedding_text for c in chunks])
        self.vector_store.index(chunks, vectors)
        self.lexical.index(chunks)
        self._indexed = True

    def retrieve(self, query: str) -> list[ScoredChunk]:
        if not self._indexed:
            raise RuntimeError("HybridRetriever.index() must be called before retrieve().")
        cfg = self.config
        q_vec = self.embedder.embed([query])[0]
        dense_hits = self.vector_store.search(q_vec, cfg.dense_top_k)
        lexical_hits = self.lexical.search(query, cfg.lexical_top_k)
        fused = reciprocal_rank_fusion(lexical_hits, dense_hits, k=cfg.rrf_k)
        candidates = fused[: cfg.rerank_top_k]
        reranked = self.reranker.rerank(query, candidates, cfg.final_top_k)
        return reranked

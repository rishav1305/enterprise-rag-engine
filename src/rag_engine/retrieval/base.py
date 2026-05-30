"""Layer 4 — Retrieval seams.

Three ABCs decouple the moving parts so any one can be swapped without
touching the others:
  * ``Embedder``    — text -> dense vector
  * ``VectorStore`` — dense ANN index (in-memory default; Qdrant/pgvector prod)
  * ``Reranker``    — re-score a candidate set with a stronger signal
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ..schemas import EnrichedChunk, ScoredChunk


class Embedder(ABC):
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) L2-normalised float32 matrix."""
        raise NotImplementedError


class VectorStore(ABC):
    @abstractmethod
    def index(self, chunks: list[EnrichedChunk], vectors: np.ndarray) -> None: ...

    @abstractmethod
    def search(self, query_vec: np.ndarray, top_k: int) -> list[ScoredChunk]: ...


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, candidates: list[ScoredChunk], top_k: int) -> list[ScoredChunk]: ...

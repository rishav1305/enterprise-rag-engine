"""In-memory cosine vector store + a Qdrant adapter seam.

The in-memory store is the default so the engine runs with no external service.
``QdrantVectorStore`` shows the production swap: same ``VectorStore`` interface,
real ANN index. (Import is lazy so qdrant-client stays an optional dependency.)
"""

from __future__ import annotations

import numpy as np

from ..schemas import EnrichedChunk, ScoredChunk
from .base import VectorStore


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._chunks: list[EnrichedChunk] = []
        self._matrix: np.ndarray | None = None

    def index(self, chunks: list[EnrichedChunk], vectors: np.ndarray) -> None:
        self._chunks = list(chunks)
        self._matrix = vectors.astype(np.float32)

    def search(self, query_vec: np.ndarray, top_k: int) -> list[ScoredChunk]:
        if self._matrix is None or len(self._chunks) == 0:
            return []
        sims = self._matrix @ query_vec.ravel()  # vectors are L2-normalised
        order = np.argsort(-sims)[:top_k]
        return [
            ScoredChunk(chunk=self._chunks[i], score=float(sims[i]), dense_rank=rank + 1)
            for rank, i in enumerate(order)
        ]


class QdrantVectorStore(VectorStore):  # pragma: no cover - requires running Qdrant
    """Production adapter. `pip install qdrant-client` and run the service."""

    def __init__(self, url: str = "http://localhost:6333", collection: str = "rag_chunks") -> None:
        from qdrant_client import QdrantClient

        self.client = QdrantClient(url=url)
        self.collection = collection
        self._chunks: dict[str, EnrichedChunk] = {}

    def index(self, chunks: list[EnrichedChunk], vectors: np.ndarray) -> None:
        from qdrant_client.models import Distance, PointStruct, VectorParams

        self.client.recreate_collection(
            self.collection,
            vectors_config=VectorParams(size=vectors.shape[1], distance=Distance.COSINE),
        )
        points = []
        for i, (c, v) in enumerate(zip(chunks, vectors)):
            self._chunks[c.chunk_id] = c
            points.append(PointStruct(id=i, vector=v.tolist(), payload={"chunk_id": c.chunk_id}))
        self.client.upsert(self.collection, points=points)

    def search(self, query_vec: np.ndarray, top_k: int) -> list[ScoredChunk]:
        hits = self.client.search(self.collection, query_vec.tolist(), limit=top_k)
        out = []
        for rank, h in enumerate(hits):
            c = self._chunks[h.payload["chunk_id"]]
            out.append(ScoredChunk(chunk=c, score=float(h.score), dense_rank=rank + 1))
        return out

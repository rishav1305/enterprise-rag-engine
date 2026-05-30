"""Reranking seam.

The default ``LexicalOverlapReranker`` is a transparent, offline cross-signal:
it boosts candidates whose tokens overlap the query and rewards exact phrase
hits. Production swaps in a cross-encoder (e.g. bge-reranker / Cohere Rerank)
behind the same ``Reranker`` ABC — the pipeline does not change.
"""

from __future__ import annotations

import re

from ..schemas import ScoredChunk
from .base import Reranker

_TOKEN = re.compile(r"[a-z0-9]+")


class LexicalOverlapReranker(Reranker):
    def rerank(self, query: str, candidates: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
        q_tokens = set(_TOKEN.findall(query.lower()))
        q_phrase = query.lower().strip()
        scored: list[tuple[float, ScoredChunk]] = []
        for sc in candidates:
            text = sc.chunk.embedding_text.lower()
            c_tokens = set(_TOKEN.findall(text))
            overlap = len(q_tokens & c_tokens) / (len(q_tokens) or 1)
            phrase_bonus = 0.25 if q_phrase and q_phrase in text else 0.0
            # blend fusion score with the rerank signal
            final = 0.5 * sc.score + 0.5 * overlap + phrase_bonus
            scored.append((final, sc))
        scored.sort(key=lambda t: -t[0])
        out = []
        for final, sc in scored[:top_k]:
            sc.score = float(final)
            out.append(sc)
        return out


class CrossEncoderReranker(Reranker):  # pragma: no cover - optional heavy dep
    """Production reranker. `pip install sentence-transformers`."""

    def __init__(self, model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model)

    def rerank(self, query: str, candidates: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
        pairs = [(query, c.chunk.embedding_text) for c in candidates]
        scores = self.model.predict(pairs)
        for sc, s in zip(candidates, scores):
            sc.score = float(s)
        return sorted(candidates, key=lambda c: -c.score)[:top_k]

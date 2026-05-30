"""BM25 lexical engine.

Lexical search is non-negotiable in the enterprise: it is the only thing that
reliably surfaces exact error codes, alphanumeric SKUs, ticket IDs, and legacy
proper nouns that dense encoders smear together. We use Okapi BM25 over the
same anchored text that the dense side embeds, so both engines see identical
content.
"""

from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from ..schemas import EnrichedChunk, ScoredChunk

_TOKEN = re.compile(r"[A-Za-z0-9_\-]+")


def _tok(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text)]


class BM25Index:
    def __init__(self) -> None:
        self._chunks: list[EnrichedChunk] = []
        self._bm25: BM25Okapi | None = None

    def index(self, chunks: list[EnrichedChunk]) -> None:
        self._chunks = list(chunks)
        corpus = [_tok(c.embedding_text) for c in chunks]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        if self._bm25 is None or not self._chunks:
            return []
        scores = self._bm25.get_scores(_tok(query))
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
        return [
            ScoredChunk(chunk=self._chunks[i], score=float(scores[i]), lexical_rank=rank + 1)
            for rank, i in enumerate(ranked)
        ]

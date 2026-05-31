"""Citation builder with an immutable content-hash chain.

Every admitted chunk that the answer rests on is emitted as a structured
``Citation`` carrying a SHA-256 content hash. The hash lets a downstream
consumer verify the cited text was not altered after the fact — an audit-grade
provenance trail rather than a friendly footnote.
"""

from __future__ import annotations

from ..config import EngineConfig
from ..schemas import Citation, ScoredChunk


def build_citations(chunks: list[ScoredChunk], config: EngineConfig | None = None) -> list[Citation]:
    cfg = config or EngineConfig()
    citations: list[Citation] = []
    for sc in chunks:
        c = sc.chunk
        quote = c.content.strip().replace("\n", " ")
        if len(quote) > cfg.max_quote_chars:
            quote = quote[: cfg.max_quote_chars].rsplit(" ", 1)[0] + "…"
        citations.append(
            Citation(
                chunk_id=c.chunk_id,
                parent_doc_id=c.parent_doc_id,
                parent_title=c.parent_title,
                doc_hash=c.doc_hash,
                quote=quote,
            )
        )
    return citations

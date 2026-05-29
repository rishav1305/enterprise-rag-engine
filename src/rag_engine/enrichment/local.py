"""Offline, deterministic contextualizer — the default.

It builds an anchor from the document title, its summary, and the chunk's
position, with zero network calls. This keeps the engine fully runnable in CI
and air-gapped environments. For production semantic anchors, swap in
``AnthropicContextualizer`` via ``RAG_CONTEXTUALIZER=anthropic``.
"""

from __future__ import annotations

from ..schemas import Document, EnrichedChunk
from .base import Contextualizer


class LocalHeuristicContextualizer(Contextualizer):
    def annotate(self, doc: Document, chunks: list[EnrichedChunk]) -> list[EnrichedChunk]:
        summary = (doc.summary or "").strip()
        scope = f" ({summary})" if summary else ""
        n = len(chunks)
        for c in chunks:
            c.contextual_anchor = (
                f"From '{doc.title}'{scope}, section {c.ordinal + 1} of {n}."
            )
        return chunks

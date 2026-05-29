"""Layer 2 — Chunk enrichment seam (Anthropic Contextual Retrieval).

A contextualizer prepends a short situating sentence to each chunk so that a
vague fragment like *"It costs $200/month"* becomes
*"This chunk discusses premium-tier pricing for Widget-X in the 2026 SaaS
Inventory Guide: It costs $200/month."* That single anchor lifts both lexical
and semantic recall, and it is the cheapest precision win in the whole stack.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import Document, EnrichedChunk


class Contextualizer(ABC):
    """Abstract base class for chunk contextualization strategies."""

    @abstractmethod
    def annotate(self, doc: Document, chunks: list[EnrichedChunk]) -> list[EnrichedChunk]:
        """Return chunks with ``contextual_anchor`` populated."""
        raise NotImplementedError

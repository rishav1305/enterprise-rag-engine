"""Multimodal embedding (P0.10 WORKER-C).

Cross-modal retrieval works when a text query and a non-text chunk embed into the
SAME vector space — so a text query can match an image/table chunk. We embed each
chunk's TEXT surface (``embedding_text`` — the caption/table-rendering/OCR text the
extractor produced) so the existing text embedder already gives cross-modal recall:
the modality differs, the embedding space is shared.

``FakeMultimodalEmbedder`` is deterministic (wraps the offline ``HashingEmbedder``),
so cross-modal tests run with no creds. A live multimodal model (Voyage-multimodal /
CLIP-style, which embeds raw pixels + text jointly) is creds-gated behind the same
``Embedder`` ABC; it would embed the raw payload, but the GOVERNANCE is identical —
the embedding never bypasses the allowlist pre-filter.
"""

from __future__ import annotations

import numpy as np

from ..retrieval.base import Embedder
from ..retrieval.embedders import HashingEmbedder
from ..schemas import EnrichedChunk


class FakeMultimodalEmbedder(Embedder):
    """Deterministic cross-modal embedder — text + caption share one space."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self._text = HashingEmbedder(dim=dim)

    def embed(self, texts: list[str]) -> np.ndarray:
        return self._text.embed(texts)

    def embed_chunks(self, chunks: list[EnrichedChunk]) -> np.ndarray:
        """Embed chunks by their TEXT surface (caption/OCR/table rendering).

        Same space as a text query, so cross-modal retrieval falls out for free —
        and a non-text chunk is embedded by its text surface, never its raw payload,
        so the index holds no raw bytes (ELASTIC + no payload-in-index leak).
        """
        if not chunks:
            return np.zeros((0, self.dim), dtype="float32")
        return self.embed([c.embedding_text for c in chunks])


__all__ = ["FakeMultimodalEmbedder"]

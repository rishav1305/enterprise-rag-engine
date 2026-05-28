"""Engine configuration. Tunable knobs live here, not scattered as magic numbers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class EngineConfig:
    # chunking
    chunk_size: int = 700           # target characters per chunk
    chunk_overlap: int = 120

    # retrieval
    embedding_dim: int = 512        # dim of the offline hashing embedder
    lexical_top_k: int = 20
    dense_top_k: int = 20
    rrf_k: int = 60                 # Reciprocal Rank Fusion constant
    rerank_top_k: int = 8           # candidates passed to the reranker
    final_top_k: int = 5            # chunks handed to governance

    # generation
    max_quote_chars: int = 240

    # backends (swap via env without touching code)
    contextualizer: str = field(default_factory=lambda: os.getenv("RAG_CONTEXTUALIZER", "local"))
    generator: str = field(default_factory=lambda: os.getenv("RAG_GENERATOR", "extractive"))
    anthropic_model: str = field(
        default_factory=lambda: os.getenv("RAG_ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
    )

    @property
    def use_anthropic(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY"))

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

    # vector path (P0.2c) — TurboVec coarse retrieval feeds a MANDATORY reranker.
    # The reranker is load-bearing (P0.2b: ~0.45 coarse recall on tight clusters,
    # rerank recovers to ~0.80+), so over-fetch a wide coarse set and ALWAYS rerank.
    vector_coarse_k: int = 200      # over-fetch from TurboVec before reranking
    vector_path_rerank_mandatory: bool = True  # documented invariant; non-disableable

    # generation
    max_quote_chars: int = 240

    # backends (swap via env without touching code)
    contextualizer: str = field(default_factory=lambda: os.getenv("RAG_CONTEXTUALIZER", "local"))
    generator: str = field(default_factory=lambda: os.getenv("RAG_GENERATOR", "extractive"))
    anthropic_model: str = field(
        default_factory=lambda: os.getenv("RAG_ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
    )

    # store backend (P0.2a) — "memory" (in-process, default) | "surrealdb".
    # Multi-setup: the same DDL serves a local self-host instance (CI/dev) AND
    # SurrealDB Cloud — only the DSN/creds differ, all env-driven (CONFIGURABLE).
    store_backend: str = field(default_factory=lambda: os.getenv("RAG_STORE_BACKEND", "memory"))
    surreal_dsn: str = field(
        default_factory=lambda: os.getenv("SURREAL_DSN", "ws://127.0.0.1:8000/rpc")
    )
    surreal_ns: str = field(default_factory=lambda: os.getenv("SURREAL_NS", "meridian"))
    surreal_db: str = field(default_factory=lambda: os.getenv("SURREAL_DB", "clearance"))
    surreal_user: str = field(default_factory=lambda: os.getenv("SURREAL_USER", "root"))
    surreal_pass: str = field(default_factory=lambda: os.getenv("SURREAL_PASS", "root"))

    @property
    def use_anthropic(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY"))

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

    # BigQuery PB-tail cost guard (P0.3a) — CONFIGURABLE, no magic numbers.
    # maximum_bytes_billed: hard cap on bytes scanned (a dry-run estimate over this
    # is REFUSED). Default 1 GB keeps the sandbox free tier safe.
    bq_max_bytes_billed: int = field(
        default_factory=lambda: int(os.getenv("BQ_MAX_BYTES_BILLED", str(1_000_000_000)))
    )
    bq_require_partition_filter: bool = field(
        default_factory=lambda: os.getenv("BQ_REQUIRE_PARTITION_FILTER", "1") != "0"
    )
    bq_dialect: str = field(default_factory=lambda: os.getenv("BQ_DIALECT", "bigquery"))

    # routing + text-to-SQL (P0.3b) — CONFIGURABLE, multi-setup.
    # router_backend: "heuristic" (regex fast-path, default) | "semantic"
    # (embedding-similarity, local deterministic encoder, no LLM in hot path).
    router_backend: str = field(default_factory=lambda: os.getenv("RAG_ROUTER", "heuristic"))
    # sql_generator: "fake" (deterministic, tests) | "groq" | "nvidia" (live,
    # OpenAI-compatible, creds-gated).
    sql_generator: str = field(default_factory=lambda: os.getenv("RAG_SQL_GENERATOR", "fake"))
    sql_llm_base_url: str = field(
        default_factory=lambda: os.getenv("RAG_SQL_LLM_BASE_URL",
                                          "https://api.groq.com/openai/v1")
    )
    sql_llm_model: str = field(
        default_factory=lambda: os.getenv("RAG_SQL_LLM_MODEL", "llama-3.3-70b-versatile")
    )

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

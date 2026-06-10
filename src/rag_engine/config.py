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
    # P0.11a W4: which AllowlistBackend the mode-router uses. "in_process" (default,
    # the canonical decision source) | "local_rebac" (zero-dep tuple kernel) |
    # "spicedb" | "oso" (gated). All are parity-guaranteed to agree with in_process.
    allowlist_backend: str = field(
        default_factory=lambda: os.getenv("RAG_ALLOWLIST_BACKEND", "in_process")
    )
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
    # opaque-schema glossary drafter (P0.4): "fake" (deterministic, tests) |
    # "groq" | "nvidia" (live, creds-gated). Uses sql_llm_base_url/model.
    glossary_drafter: str = field(
        default_factory=lambda: os.getenv("RAG_GLOSSARY_DRAFTER", "fake")
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

    # semantic cache (P0.7) — CONFIGURABLE, no magic numbers. Permission-aware:
    # the cache key incorporates the session auth scope AND governance is re-applied
    # on hit (see cache/semantic_cache.py). All knobs env-overridable + validated.
    cache_enabled: bool = field(
        default_factory=lambda: os.getenv("RAG_CACHE_ENABLED", "1") != "0"
    )
    cache_similarity_threshold: float = field(
        default_factory=lambda: float(os.getenv("RAG_CACHE_SIMILARITY", "0.93"))
    )
    cache_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("RAG_CACHE_TTL_SECONDS", "900"))
    )
    cache_max_entries: int = field(
        default_factory=lambda: int(os.getenv("RAG_CACHE_MAX_ENTRIES", "1024"))
    )
    # "memory" (in-process default) | "surreal" (durable, binary/creds-gated).
    cache_backend: str = field(
        default_factory=lambda: os.getenv("RAG_CACHE_BACKEND", "memory")
    )
    # P0.11a W6: multimodal payload size bound (ELASTIC — guarded_extract rejects +
    # audits an oversized binary so a giant upload can't blow memory). Default 25 MiB.
    multimodal_max_payload_bytes: int = field(
        default_factory=lambda: int(os.getenv("RAG_MM_MAX_PAYLOAD_BYTES",
                                              str(25 * 1024 * 1024)))
    )

    # self-RAG / corrective loop (P0.8) — CONFIGURABLE, no magic numbers. The loop
    # is BOUNDED (RESILIENT: max_iterations caps re-retrieval so it can't spin).
    selfrag_enabled: bool = field(
        default_factory=lambda: os.getenv("RAG_SELFRAG_ENABLED", "1") != "0"
    )
    selfrag_max_iterations: int = field(
        default_factory=lambda: int(os.getenv("RAG_SELFRAG_MAX_ITERATIONS", "3"))
    )
    selfrag_relevance_threshold: float = field(
        default_factory=lambda: float(os.getenv("RAG_SELFRAG_RELEVANCE", "0.3"))
    )
    selfrag_groundedness_threshold: float = field(
        default_factory=lambda: float(os.getenv("RAG_SELFRAG_GROUNDEDNESS", "0.6"))
    )
    # "fake" (deterministic, tests/offline default) | "openai" (Groq/NVIDIA, gated).
    selfrag_grader: str = field(
        default_factory=lambda: os.getenv("RAG_SELFRAG_GRADER", "fake")
    )

    def __post_init__(self) -> None:
        # Schema validation (CONFIGURABLE pillar): invalid config REFUSES to start —
        # never silently falls back to a default that could mask a misconfiguration.
        if not (0.0 < self.cache_similarity_threshold <= 1.0):
            raise ValueError(
                f"cache_similarity_threshold must be in (0.0, 1.0] (cosine), got "
                f"{self.cache_similarity_threshold}"
            )
        if self.cache_ttl_seconds <= 0:
            raise ValueError(
                f"cache_ttl_seconds must be > 0, got {self.cache_ttl_seconds}"
            )
        if self.cache_max_entries <= 0:
            raise ValueError(
                f"cache_max_entries must be > 0, got {self.cache_max_entries}"
            )
        if self.cache_backend not in ("memory", "surreal"):
            raise ValueError(
                f"cache_backend must be 'memory' or 'surreal', got {self.cache_backend!r}"
            )
        if self.allowlist_backend not in ("in_process", "local_rebac", "spicedb", "oso"):
            raise ValueError(
                f"allowlist_backend must be in_process|local_rebac|spicedb|oso, got "
                f"{self.allowlist_backend!r}"
            )
        # self-RAG knobs
        if self.selfrag_max_iterations < 1:
            raise ValueError(
                f"selfrag_max_iterations must be >= 1 (RESILIENT bound), got "
                f"{self.selfrag_max_iterations}"
            )
        if not (0.0 < self.selfrag_relevance_threshold <= 1.0):
            raise ValueError(
                f"selfrag_relevance_threshold must be in (0.0, 1.0], got "
                f"{self.selfrag_relevance_threshold}"
            )
        if not (0.0 < self.selfrag_groundedness_threshold <= 1.0):
            raise ValueError(
                f"selfrag_groundedness_threshold must be in (0.0, 1.0], got "
                f"{self.selfrag_groundedness_threshold}"
            )
        if self.selfrag_grader not in ("fake", "openai"):
            raise ValueError(
                f"selfrag_grader must be 'fake' or 'openai', got {self.selfrag_grader!r}"
            )

    @property
    def use_anthropic(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY"))

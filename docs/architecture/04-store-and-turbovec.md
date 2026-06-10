# 4 — Store + TurboVec

## SurrealDB — the unified multi-model store

`store/surreal.py::SurrealStore` is the one place that speaks SurrealQL, and the **same
instance** serves catalog + ACLs + all four retrieval modes. `store/schema.py::ddl_statements`
defines the schema (SurrealDB 3.1.x, validated by spike S2 — all `DEFINE … OVERWRITE` for
idempotent re-apply):

- `chunk` table — chunk text + vector + `asset_id` + `cls` + `level` (the governance currency).
- graph tables (`supplier`/`contract`/`component`/`ticket`) + a `links` **RELATION** edge
  (`chunk → chunk`) for graph traversal.
- a `chunk_vec` **HNSW** index (`DIMENSION … DIST COSINE TYPE F32`, Voyage-3-large 1024-dim
  default) and full-text **BM25** indexes (`chunk_ft` on text, `ticket_ft` on summary) via a
  `meridian_text` analyzer.
- `query_cache` (the durable semantic cache, deep dive [§9](09-semantic-cache.md)).

All record ids are bound as `RecordID` **params** (no SurrealQL injection — SECURE). Key
methods: `upsert_chunk`, `get_chunk_row`, `delete_chunk` (+ links cascade, P0.9),
`chunks_by_version` (re-embed migration), `chunk_security_rows` (the allowlist projection: ids +
ACLs only, no text/vector blobs — ELASTIC), and the three allowlist-scoped mode queries
`graph_neighbors` / `structured_rows` / `fulltext_search` (deep dive [§5](05-retrieval.md)).

**Multi-setup:** identical code for a local self-host instance (CI/dev, via the ephemeral
`surreal_local` test fixture) and SurrealDB Cloud — only the DSN/creds differ (CONFIGURABLE).

## TurboVec — the compressed vector index

`retrieval/turbovec_index.py::TurboVecIndex` wraps `turbovec.IdMapIndex` (**TurboQuant**,
`bit_width=4`, S1-validated cold-load). The vectors-by-id live in SurrealDB; TurboVec serves the
ANN — a deliberate split (spike S2) that keeps the compressed index loadable into a stateless
orchestrator.

**The headline property:** `search(query_vec, k, allowlist_chunk_ids=…)` enforces permissions
**at the index** — a chunk not on the session's allowlist is never a candidate
(drop-before-search). An **empty allowlist returns nothing** (fail-closed). This is stage 1 of
governance for the vector path; `tests/test_allowlist_prefilter.py` proves an unauthorized
vector is excluded at the index even when it is the nearest neighbour.

The vector path uses a wide coarse over-fetch (`vector_coarse_k`) then a **mandatory rerank**
(non-disableable — P0.2b found ~0.45 coarse recall on tight clusters, rerank recovers to ~0.80+).

**Wired-live vs gated:** TurboVec is a pinned dev dependency (the recall + pre-filter tests are
0-skip in CI). SurrealDB Cloud + Voyage embeddings are creds-gated; the offline path uses the
deterministic `HashingEmbedder` (no model download).

# 9 — Semantic cache (permission-aware, fail-closed)

A semantic cache that keys only on query-embedding similarity is a **permission bypass**: it
would serve User A's cached answer (content A is cleared for) to User B who is not. CLEARANCE's
cache (`cache/`) is permission-aware by construction, defended **two ways** (defense in depth).

## Defense 1 — scope-isolated key

`cache/key.py::AuthScope.from_session(session)` captures the **governance-relevant identity**:
`(clearance_level, sorted(roles))` — exactly what `access.evaluate` consults (need-to-know is
per-chunk, matched against these roles). `fingerprint()` is a stable, role-order-independent
sha256. Cache entries are **namespaced by `scope_fp`**, so a lookup only ever scans entries with
the requester's exact scope — a different clearance/role-set **cannot reach** another scope's
entries.

## Defense 2 — re-govern on hit

`cache/semantic_cache.py::SemanticCache.get(query, session, govern_fn)`: among same-scope entries
above the cosine threshold, the best match's stored chunk ids are **re-governed** via the caller's
`govern_fn` (in the pipeline, this re-runs `SecurityFilter` — `pipeline.py::_govern_fn`, NOT
identity). The contract is **miss-on-any-redaction** (the fail-closed sharpness): if re-governance
changes the authorized set **at all** (any chunk now denied), it is a **MISS** — the pipeline
regenerates fresh. The stored answer is opaque (synthesized from the full chunk set) and cannot be
safely re-masked, so serving it with merely-trimmed ids would leak the denied content.

## Mechanics

- cosine match over an injected `Embedder` (deterministic `HashingEmbedder` default, no creds);
- **TTL + LRU** eviction (`max_entries`) — bounded footprint (ELASTIC);
- `cache/observability.py::record_cache_hit` emits a metric-only `cache_lookup` span + funnel
  note + an attributable `AuditSink` `cache_hit` event (deep dive [§8](08-funnel-and-observability.md))
  — a hit is observable and **does not bypass the audit trail**, carrying no chunk content;
- `cache/surreal_cache.py::SurrealCacheStore` is the durable backend (gated); `invalidate_chunk`
  (delete/reclassify) + `invalidate_version` (re-embed) are the CDC seams (deep dive
  [§10b](10b-cdc-and-reembedding.md)).

## Proofs

`tests/test_cache_permission.py` is the cache leak oracle: a high-clearance session populates the
cache; a semantically-identical low-clearance query gets a **MISS** (scope key), never the
high-clearance answer. Mutation-proven: drop the scope from the key → cross-clearance leak (in-mem
AND durable) → fails. The govern_fn's sole-defense role is proven by
`tests/test_pipeline_cache.py::test_cache_hit_then_revoke_is_re_redacted` (same-scope hit after the
chunk is reclassified-tightened — `govern_fn`→identity leaks).

**Wired-live vs gated:** the in-memory cache is wired into `RAGPipeline.query` (P0.11a W2) with the
real `govern_fn`; the durable SurrealDB cache is gated. Config: `cache_enabled` /
`cache_similarity_threshold` / `cache_ttl_seconds` / `cache_max_entries` / `cache_backend`.

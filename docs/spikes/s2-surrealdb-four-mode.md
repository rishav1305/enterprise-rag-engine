# Spike S2 — SurrealDB four-mode at derivative scale

**Date:** 2026-06-09 · **Owner:** Shuri · **Type:** throwaway probe (no product code) · **Status:** ✅ KEEP SurrealDB for graph/SurrealQL/full-text/catalog; TurboVec owns vector ANN (as designed)

> **Question:** Can ONE SurrealDB instance serve all four retrieval modes (vector, graph, SurrealQL/structured, full-text) plus the catalog + ACL spine, at the indexable-derivative scale, on a free-tier-sized footprint — and does a local self-host instance work for dev/CI while titan-pc is down?

## 1. Method
- **SurrealDB 3.1.3** (`surreal` CLI) + **Python SDK `surrealdb==2.0.0`** (abi3 wheel). Local `surreal start` — both **in-memory** (`memory`) and **file-backed** (`surrealkv://`) instances, the self-host dev/CI path (titan-pc is down, so no remote self-host dependency).
- Connection: `ws://127.0.0.1:PORT/rpc`, root auth, `USE ns db`. Connection string is config (CONFIGURABLE) → swaps to **SurrealDB Cloud** with no code change.
- Workload at derivative scale: 5k vector rows (64-dim), ~5k graph nodes (500 supplier / 1.5k contract / 3k component), 5k structured sale rows, 2k full-text ticket rows, plus catalog + ACL rows — all in one instance/namespace.

## 2. Results (one instance, all modes)

| Mode | Operation | Latency | Correctness |
|---|---|---|---|
| **Catalog + ACL** | `CREATE asset`, `SELECT … WHERE level >= 5` | 0.3 ms | ✅ ACL filter returns only L5 asset |
| **Vector** | HNSW index build + `vec <|k,COSINE|> $q` KNN | insert 901 ms / KNN 37 ms | ⚠️ returns fewer than k (see §3) |
| **Vector pre-filter** | `WHERE owner='PUB' AND vec <|k,COSINE|> $q` | 6.8 ms | ✅ structured predicate + KNN composes (permission pre-filter at the DB) |
| **Graph** | record links + `SELECT ->contract FROM supplier:1` traversal | build 398 ms / traverse 0.7 ms | ✅ multi-hop traversal works |
| **SurrealQL** | `GROUP BY segment, math::sum(amount), count()` | 5.6 ms | ✅ warehouse-style aggregation |
| **Full-text** | `FULLTEXT` index + `summary @@ 'timeout shard'` | 1.5 ms | ✅ BM25 search hits |
| **Exact-id** | `WHERE code = 'ERR-DB-0042'` (the typo/exact leg) | 0.9 ms | ✅ exact match |

- **File-backed persistence** (`surrealkv:///tmp/sdb_file`): write+read survives — durable self-host path confirmed.
- **Footprint:** file-backed instance ≈ 100 MB RSS at this scale (fits the free-tier 512 MB envelope). (A long-lived in-memory instance accumulated several GB across repeated spike runs — an artifact of not restarting, not steady-state.)

## 3. Honest caveats (drive the architecture)
- **Vector KNN returned fewer than k** even with `LIMIT k` and tuned HNSW (`EFC 150 M 12`) on random 64-dim vectors. SurrealDB's ANN is usable but **less battle-tested than a specialised index** — exactly the spec's stated caveat. **This is WHY the architecture puts the real vector ANN in TurboVec** (P0.2b), with SurrealDB holding **vectors-by-id + metadata**. S2 confirms that division of labour is the right call, not a regression.
- **Syntax drift 3.x vs older docs:** vector index is `HNSW … TYPE F32` (not `MTREE … DIST` standalone); KNN operator is `<|k,DIST|>`; full-text is `FULLTEXT ANALYZER` (not `SEARCH ANALYZER`); `DELETE` on a missing table errors → use `REMOVE … IF EXISTS`. P0.2a DDL must target 3.1.x syntax.

## 4. Verdict — ✅ KEEP
One SurrealDB instance cleanly serves **graph + SurrealQL + full-text + catalog + ACL + vectors-by-id**, with structured-predicate-plus-KNN composition for the vector pre-filter. The vector *ANN* stays in TurboVec (P0.2b) per the design. Local self-host (in-memory for CI, file-backed for durable dev) is a real, tested path independent of titan-pc; the same engine + connection-string config points at **SurrealDB Cloud** for the hosted demo — multi-setup satisfied.

## 5. P0.2a implications
- Model the catalog/ACL/glossary + four modes behind the existing `Connector`/`CatalogRegistry` surface; the 210-cell oracle + leak demo + C1 masking enforcement must stay green through the in-memory→SurrealDB swap (regression parity = the key gate).
- Provide TWO tested connection profiles (CONFIGURABLE): `surrealdb-local` (CI/dev) and `surrealdb-cloud` (hosted) — same DDL, env-driven DSN.
- Use 3.1.x DDL: HNSW vector index, FULLTEXT search index, `REMOVE … IF EXISTS` for idempotent schema.

## 6. Reproduce
Throwaway harness `/tmp/s2_spike.py` (venv `/tmp/s2venv`, `surreal` at `~/.surrealdb/surreal`). Not committed — this doc is the artifact.

*Spike complete. Feeds P0.2a (SurrealDB unified store) DDL + dual connection profiles; confirms TurboVec retains the vector ANN role for P0.2b.*

# CLEARANCE / P0 — Approved Decomposition (14 phases, roadmap-inclusive)

**Date:** 2026-06-08 · **Owner:** Shuri · **Status:** CEO-approved 2026-06-08 · **Repo:** `enterprise-rag-engine`

> Source spec: `docs/superpowers/specs/2026-06-08-clearance-polystore-design.md` · World bible: `docs/meridian-org-and-data.md` · Build philosophy: NO YAGNI; multi-setup paths real+tested; 7 pillars (SOVEREIGN dropped). Ledger surface spec: `marketing/portfolio_app` branch `docs/engineering-ledger-spec`.

Each phase is an increasing-impact increment that ships demoable value; the destination is the full robust system. Roadmap items are pulled in and ordered by impact, never dropped. Each phase ends with the leak-audit oracle green + eval gate passing + L1–L7 per the verification matrix.

## Build order (de-risk earliest)

| Phase | Increment | Expanded-scope / multi-setup notes | Size |
|---|---|---|---|
| **S1 spike** | TurboVec-in-serverless probe | ✅ KEEP verdict (`docs/spikes/s1-turbovec-serverless.md`) | done |
| **P0.1a** Meridian Data Foundation | full reusable data estate | 16 synthetic sources (+payroll/benefits/recruiting/expenses/tax/treasury) + 7 real fixtures + legacy_mart + personas/matrix | L |
| **P0.1b** Catalog + Governance-v2 | catalog registry, SecurityContext→assets/columns, leak oracle bound to matrix | `Connector` ABC, column masking | M |
| **P0.2a** SurrealDB spine | unified store: graph/SurrealQL/full-text/catalog | self-host (titan-pc) AND Cloud both built+tested | M |
| **P0.2b** TurboVec vector index | compressed ANN + vector allowlist pre-filter + offline build — **BUILT + unit-proven, NOT yet wired into live retrieval** | + Qdrant fallback adapter real & tested; recall re-validated on real embeddings (~0.45 tight / ~0.90+ text; reranker load-bearing) | L |
| **P0.2c** Retrieval integration | **DONE** — `TurboVecRetriever` wired into the pipeline (vector mode), **reranker mandatory** on the coarse set, vector queries through the **allowlist pre-filter** + downstream C1; **E2E C1-over-vector** (class-D via live TurboVec → `[REDACTED]`; **hardened** to assert the L5 chunk never enters the candidate set, so it fails if the pre-filter is bypassed). Closed the build-vs-wired gap. | live path uses an in-memory `ChunkSource` (store adapter → P0.2d) | M |
| **P0.2d** Store-backed retrieval + ELASTIC | **DONE** — `SurrealChunkSource` implements the `ChunkSource` protocol over the SurrealDB `chunk` table (`get_chunk` full hydrate; `SecurityContext` from cls/level via shared `_CLASS_ROLES`); **store-backed C1-over-vector E2E** proves live enforcement against a real SurrealDB (class-D → `[REDACTED]`, L5 never in candidate set — hardened). ELASTIC: `all_chunk_security()` now **projects ids+ACLs only** (`SELECT id, asset_id, cls, level`) — no text/vector blobs per query. **Remaining ELASTIC follow-on:** `authorized_chunk_ids` is still O(N) (evaluates every chunk's ACL) — sub-linear ReBAC list-objects (Oso/SpiceDB, spec §9) tracked for a later phase. | both stores live (in-mem + SurrealDB-backed) | M |
| **P0.3a** BigQuery PB tail + SQL safety | text-to-SQL target, cost guard, `sqlglot` AST gate | tiered parsers (Docling+LlamaParse+Reducto) | M |
| **P0.3b** Text-to-SQL agent | NL→SQL over derivative vs PB-tail routing | semantic-router adaptive routing | M |
| **P0.4** Opaque-schema glossary | profiler + miner + LLM-drafter + drift CI | full glossary governance | L |
| **P0.5** Funnel + observability | funnel math, provenance, tracing | Langfuse Cloud AND self-host both wired | S |
| **P0.6** Governance pre-filter ALL modes | extend index pre-filter beyond vector → graph/SQL/lexical | Oso Cloud + SpiceDB self-host both real (roadmap pulled in) | L |
| **P0.7** Semantic caching | per-tenant embedding-keyed cache | roadmap pulled in | M |
| **P0.8** Self-RAG + agentic loop | corrective retrieval + agentic backend (LangGraph behind router ABC) | roadmap pulled in | L |
| **P0.9** CDC/streaming + re-embedding/version-migration | freshness + index versioning | roadmap pulled in | L |
| **P0.10** Multimodal where it fits | doc-image/table retrieval | roadmap pulled in | M |
| **P0.11** Demo surface + L.x Ledger | `/projects/clearance` + Ledger band | portfolio_app repo; L7 visual | M |

## Dependency graph

```
S1 ─► P0.1a ─► P0.1b ─┬─► P0.2a ─► P0.2b ─► P0.2c ─► P0.2d ─┐
                      └─► P0.3a ─► P0.3b ─────────────────┤
                                                          ├─► P0.4 ─► P0.5 ─► P0.6 ─► P0.7 ─► P0.8 ─► P0.9 ─► P0.10 ─► P0.11
                      (P0.2a ∥ P0.3a parallel; both need only P0.1b)
                      (P0.2c wired P0.2b's index+pre-filter into live retrieval — DONE)
                      (P0.2d: store-backed ChunkSource adapter + O(N) allowlist fix; before/with P0.3b)
```

## Spikes
- **S1 TurboVec-in-serverless** ✅ done — KEEP.
- **S2 SurrealDB 4-mode** — first task inside P0.2a.
- **S3 Wren-AI-vs-glossary** — first task inside P0.4.
- **S4 BigQuery cost guard** — first task inside P0.3a.

## Workflow
Git worktree per phase; executing-plans in batches-of-3; code-reviewer between batches; finishing-a-development-branch at end. Dual remote (GitHub public + Gitea private), `git-remote-policy` verified before first GitHub push. Gates are mandatory CEO pauses — drive up, stop, report.

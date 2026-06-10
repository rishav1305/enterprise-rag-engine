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
| **P0.3a** BigQuery PB tail + SQL safety | **DONE** — `GuardedBigQuery` 4-gate wrapper: `sql/ast_gate` (read-only sqlglot — refuse DML/DDL/injection) + `sql/cost_guard` (mandatory partition filter + `maximum_bytes_billed` via dry-run) + transpile; config-driven cap/partition (CONFIGURABLE). Warehouse assets (NYC TLC/GDELT/TPC-DS) governed like everything else (masked coords/email). All unit tests LOCAL/no-creds (S4-proven contract); live path creds-gated `@pytest.mark.bq`. make ci: 213/0-skip. | tiered parsers (Docling+LlamaParse+Reducto) → P0.3b/ingestion follow-on | M |
| **P0.3b** Text-to-SQL agent | **DONE** — `TextToSqlAgent`: NL → `SqlGenerator` draft → `GuardedBigQuery` (P0.3a gates, can ONLY emit guarded SQL) → **result rows MASKED before the model** (🔴 hard gate: masked column `[REDACTED]`, raw never in answer/citations/generator-input — E2E proven-to-bite) → answer. FakeSqlGenerator (no-creds core) + OpenAICompatGenerator (Groq/NVIDIA live, creds-gated). **SemanticRouter** adopted (semantic-router + deterministic LOCAL HashingEmbedder DenseEncoder, no LLM in hot path) behind QueryRouter ABC; HeuristicRouter fast-path kept. make ci: 249/0-skip. | tiered parsers → ingestion phase | M |
| **P0.4** Opaque-schema glossary | **DONE** — first-party (S3 verdict). `enrichment/schema_glossary/`: profiler (value stats) + view_miner (sqlglot lineage, **PER-TABLE**: `tbl_44.text_2`=name vs `tbl_71.text_2`=status) + drafter (FakeGlossaryDrafter core / LlmGlossaryDrafter live) + build_glossary (mined HIGH > drafted LOW) + drift CI + resolver. 🎯 text-to-SQL retrieves over the **GLOSSARY not the raw schema** (NL "name" → `SELECT text_2 FROM tbl_44`); per-table masking respected; glossary in SurrealDB. make ci 289/0-skip. | built standalone (pipeline-wire follow-on) | L |
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
- **S1 TurboVec-in-serverless** ✅ done — KEEP (`docs/spikes/s1-turbovec-serverless.md`).
- **S2 SurrealDB 4-mode** ✅ done — KEEP (`docs/spikes/s2-surrealdb-four-mode.md`).
- **S3 Wren-AI-vs-glossary** — first task inside P0.4 (decision pending — default: keep the first-party build).
- **S4 BigQuery cost guard** — first task inside P0.3a.

## Tracked follow-ons (not yet built — explicit so they aren't lost)
- **Recall on REAL Voyage embeddings (not the CI HashingEmbedder):** P0.2b re-validated recall on clustered + HashingEmbedder vectors (honest ~0.45 tight / ~0.90+ text; reranker recovers). The production embedder is Voyage-3-large — recall on *real Voyage* embeddings is a **creds-gated** validation to run when a Voyage key is available (the offline build path). Until then the reranker-load-bearing finding stands. → fold into P0.2b-followup / the offline-build phase.
- **Adaptive router:** still the regex `HeuristicRouter`. **semantic-router** (spec §9, MIT, local, embedding-similarity) replaces it on the vector path. → P0.3b ("router learns indexable-derivative vs PB-tail") is the natural home; adopt semantic-router there.
- **ReBAC sub-linear allowlist:** `authorized_chunk_ids` is O(N)/query (P0.2d note). Oso/SpiceDB list-objects (spec §9) → P0.6 (pre-filter all modes) or its own task.
- **Malformed-row audit:** TRANSPARENT logging added in the retro (chunk_source drops are logged); a durable audit-sink record for dropped governance rows is a P0.5 (observability) item.
- **Index-level pre-filter for graph/SQL/lexical modes:** P0.2 delivered it for the *vector* mode only; the other modes still post-filter → P0.6.
- **Wire text-to-SQL agent + GuardedBigQuery into the live pipeline/router** (P0.3b governance advisory): the agent is built standalone (like GuardedBigQuery, the TurboVecRetriever before P0.2c). Integration: route warehouse-SQL queries through `TextToSqlAgent` from `RAGPipeline`; derive the `mask` flag from the real `GovernanceDecision` over the warehouse asset (session-derived, NOT a literal bool); source the `ColumnPolicy` set from the catalog asset (single governance source, not the agent's `masked_columns` kwarg). → integration/P0.6-era work, pairs with the other pipeline-wiring follow-ons.

## Workflow
Git worktree per phase; executing-plans in batches; **direct review between batches + Friday's independent review fan-out at each phase completion**; finishing-a-development-branch at end. Push branches + `main` to **GitHub** (Gitea skipped while titan-pc down). **Per-phase CEO pause WAIVED for the autonomous completion run** (CEO directive 2026-06-09) — quality gates stay; stop only for genuine blockers (missing creds where a phase's CORE needs them, infra down).

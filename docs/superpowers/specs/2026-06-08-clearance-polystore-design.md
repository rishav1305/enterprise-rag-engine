# CLEARANCE — Poly-Store, PB-Scale, Permission-Aware RAG

**Design spec** · 2026-06-08 · project `enterprise-rag-engine` (P0 flagship of the Engineering Ledger)

> Sibling docs: the Ledger umbrella spec lives in `portfolio_app/docs/superpowers/specs/2026-06-08-engineering-ledger-design.md`. This doc is P0's architecture spec **and** the seed of its public `approach.md`.

---

## 1. Thesis (the one paragraph)

Enterprise RAG is not a product category and the retrieval algorithm is the commoditized 30%. The moat is the **70% everyone skips**: messy multi-vertical data integration, a permission model that travels into the index, provenance/citations, freshness, and evaluation. CLEARANCE is built around that 70%. Its headline claim — **"I can manage petabytes and run RAG over them across all five layers"** — is demonstrated honestly: you never embed a petabyte; you build the **funnel** that turns PB of raw enterprise data into the ~thousands of candidates a single query actually touches, route each query to the **right backend** (vector / warehouse text-to-SQL / graph / lexical) over the **right partition**, and **drop unauthorized content before it can ever reach the model** — proven by an adversarial leak test that fails CI on any leak.

The demonstrable promise: *the same architecture that governs a 4-document corpus funnels a petabyte — here is the math and the routing that make PB tractable.*

---

## 2. Current state — what already exists (the bundle)

The `enterprise-rag-engine` repo (extracted from `enterprise-rag-engine.bundle`, full git history preserved) is a **working, offline, pure-Python RAG engine** with five swappable ABC layers:

| Layer | Module | Built today |
|---|---|---|
| L1 Ingestion | `ingestion/markdown_loader.py` | Markdown loader + `chunk_document`; RBAC via Pydantic `SecurityContext` |
| L2 Enrichment | `enrichment/{local,anthropic_contextualizer}.py` | Local heuristic contextual anchors; Anthropic Contextual Retrieval (optional) |
| L3 Routing | `routing/heuristic_router.py` | Regex/keyword classifier → `ADVANCED_HYBRID` / `GRAPH_RAG` / `AGENTIC_LOOP` |
| L4 Retrieval | `retrieval/{hybrid,lexical,embedders,fusion,rerank,vector_store}.py` | BM25 ∥ dense → RRF → cross-encoder rerank (`ADVANCED_HYBRID` only) |
| L5 Governance | `governance/{access,filter,citations,audit}.py` | Permission-aware **post-filter** (drop-before-model), citations, audit trail |
| — Generation | `generation/{extractive,anthropic_generator}.py` | Extractive (offline) or Claude (optional) |
| — Eval | `evaluation/{metrics,gate}.py` | Retrieval metrics + CI quality gate |
| — Service | `api.py` | FastAPI |

**Key facts that make this credible:**
- **Runs offline, zero model downloads** (`pydantic`, `rank-bm25`, `numpy`, `fastapi`); Anthropic / Qdrant / pgvector / sentence-transformers are *optional, swappable* backends.
- **`SecurityContext`** is a frozen Pydantic model: `allowed_roles[]` + `clearance_level (0–5)` + `owner_department`. A chunk inherits the clearance of its source.
- **`make demo`** runs the leak demo: an `INTERN` adversarial query has restricted chunks **dropped before generation** and audited; the same query as `CFO` returns them. The difference is the session token, not the index.
- **`config.py`** already honors the CONFIGURABLE pillar — tunables centralized, backends env-swappable, no magic numbers.

**What is NOT built yet:** `GRAPH_RAG` and `AGENTIC_LOOP` are router *targets* with no backends; there is no warehouse / text-to-SQL path, no multi-connector catalog, no opaque-schema glossary, no big-data funnel, no partition pruning. The post-filter is post-retrieval (not index-level pre-filter). **That gap is this project.**

---

## 3. Target architecture — poly-store over a unified governed catalog

Decision (locked): **full poly-store** — and **hosted-backend model**: nothing large is loaded on titan-gpu. The demo *pipes* from **managed/free-tier cloud stores** and **already-hosted public datasets** (most are queryable in place), with a **stateless orchestrator** (Vercel Python serverless, the PMB pattern) holding only credentialed connectors. This keeps the demo always-available without an always-on local box, and lets us query genuinely massive hosted datasets rather than mock local loads.

> **Note (PROJECT-M drops SOVEREIGN):** as of 2026-06-08 the SOVEREIGN pillar does not apply under `~/project-m` (see memory `project-m-drops-sovereign-pillar`). License color, offline/airgap, and "no external calls in hot path" no longer constrain choices here — so we use best-of-breed managed/SaaS backends freely. The engine *remains* offline-capable (a nice-to-have we can still mention as a selling point), but availability + capability win. The other 7 pillars still apply in full.

```
                         ┌──────────── ADAPTIVE ROUTER (L3, extended) ──────────┐
   query + Session ────► │ complexity classifier + RETRIEVAL-MODE selector +    │
                         │ partition pruner (tenant / time / geography / vert.) │
                         └──┬───────────────────────────────────────┬──────────┘
                            │ indexable derivative                   │ true-PB tail
                   ┌────────▼─────────────────────────────────┐  ┌──▼──────────────────┐
                   │ SurrealDB — UNIFIED MULTI-MODEL STORE      │  │ EXTERNAL HOSTED      │
                   │ "everything in one place" (system of record│  │ (query in place)     │
                   │   • graph edges     (multi-hop traversal)   │  │   • BigQuery public  │
                   │   • structured      (SurrealQL ≈ text-to-SQL│  │     (NYC TLC, GDELT) │
                   │   • full-text       (exact ID / typo / code)│  │     text-to-SQL      │
                   │   • chunk text + ACLs + catalog + glossary  │  │   • Common Crawl /   │
                   │   • vector IDs ↔ TurboVec (below)           │  │     S3 (catalog-only)│
                   └───┬────────────────────────────────────────┘  └──┬──────────────────┘
                       │  ┌──────────────────────────────────────┐    │
                       │  │ TurboVec — compressed VECTOR INDEX      │   │
                       │  │ TurboQuant 16× (384 B/vec) · loads into │   │
                       │  │ the serverless orchestrator · ALLOWLIST │   │
                       │  │ filter = permission PRE-filter at index │   │
                       │  └──────────────────────────────────────┘    │
                            └────────── coarse → fine → rerank ────────┘
                                         │ candidate set (~thousands → final_top_k)
                               ┌─────────▼──────────┐
                               │ GOVERNANCE (L5)     │ permission-blind retrieve;
                               │ pre-filter at index │ explicit + audited enforce;
                               │ + drop-before-model │ column masking per asset
                               │ + citations + audit │
                               └─────────┬──────────┘
                                         ▼ Generation (admitted context only)

 L1 INGESTION : connectors register CATALOG METADATA into SurrealDB (never bulk-embed PB)
 L2 ENRICHMENT: contextual anchors + OPAQUE-SCHEMA GLOSSARY (text_2 → "customer name")
```

**SurrealDB is the system of record and catalog spine** — one engine for graph, structured (SurrealQL), full-text, chunk text, ACLs, the catalog + `SecurityContext`, and the glossary, with stable record IDs that map to vectors. The router selects a **retrieval mode** rather than a separate service. **TurboVec is the vector index** (not merely a pre-compressor): Google's **TurboQuant** at ~16× compression (≈384 B/vector) means the ANN index is small enough to **load directly into the stateless serverless orchestrator**, and its **allowlist filtered search lets us enforce permissions as a pre-filter at the vector index** — the at-scale evolution of today's post-filter, for the vector mode. SurrealDB holds the durable vectors-by-ID and metadata; TurboVec serves the compressed similarity search. Every connector registers assets into the one catalog (vertical, scale, masking policy); adding a source is a connector + a mapping rule, never a governance change.

**Why a tail still lives outside SurrealDB:** the genuinely-PB sources (Common Crawl, GDELT) can't and shouldn't be ingested — they stay **catalog-registered and queried in place** (BigQuery public datasets for structured/text-to-SQL; S3 for object/catalog-only). This *is* the funnel: SurrealDB holds the reduced indexable derivative; the PB tail is reached by routed, partition-pruned queries against hosted sources. Honest caveat to document: SurrealDB's vector/graph/full-text at extreme scale is less battle-tested than specialized stores — fine for the indexable derivative; the external tail is exactly why we don't force PB into it.

### 3.1 Retrieval modes & datasets (hosted)

**Tier A — SurrealDB unified store** (SurrealDB Cloud free tier, or self-host; one engine, four modes):

| Mode | Engine / feature | Real dataset (reduced derivative) | Notes |
|---|---|---|---|
| Vector | **TurboVec** (TurboQuant 16×) index; IDs ↔ SurrealDB | **Wikipedia/Wikimedia** KB embeddings | compressed ANN; allowlist = permission pre-filter; loads into orchestrator |
| Graph | SurrealDB record links / edges | supplier↔contract↔component subset | multi-hop traversal |
| Structured | SurrealDB SurrealQL tables | curated dimensional sample (TPC-DS-shaped) | the "act like a warehouse" mode |
| Full-text | SurrealDB full-text index | identifiers, error codes, names | the exact-ID / typo leg |
| Catalog | SurrealDB tables | catalog + `SecurityContext` + glossary + chunk text + vectors-by-ID | the governed spine |

**Tier B — external hosted (the PB tail, queried in place, never ingested):**

| Source | Hosted where | Scale (stated) | Role |
|---|---|---|---|
| **NYC TLC** trips | BigQuery public dataset | ≈1.6B rows | real partition-pruned **text-to-SQL** target |
| **GDELT** events | BigQuery public dataset | billions, 15-min cadence | text-to-SQL / freshness story |
| **Common Crawl** | AWS S3 public | PB-scale | **catalog-only** (funnel math, provenance) |
| **SEC EDGAR / data.gov** | public APIs | ≈16M filings | document connectors (sample pulls) |

Every source carries a **clickable provenance link** + **scale badge** (e.g. `≈1.6B rows · ~400 GB`) in the UI, so the scale claims are verifiable. The **stateless orchestrator** (Vercel Python serverless) holds only credentialed connectors to SurrealDB + BigQuery + S3/APIs — no data on titan-gpu, no always-on box.

### 3.2 The funnel (the hero narrative)

```
   PB raw  ──tier/dedupe (MinHash)──►  single-digit TB indexable
           ──embed only what matters──►  ~100s GB vectors
           ──structured pre-filter────►  ~thousands of candidates / query
           ──ANN/BM25 coarse──────────►  ~hundreds
           ──cross-encoder rerank─────►  final_top_k (=5) to governance → model
```
Rendered as the centerpiece visual with explicit math per stage. **Filter-before-search** (structured predicate → partition pruning) is stated as the single biggest scaling lever.

### 3.3 The opaque-schema semantic glossary (the differentiator)

For warehouses where column/table names carry no meaning (`text_2`, `tbl_44`):
1. **Profile** values (regex/format, cardinality, null rate, distributions, FK overlap).
2. **Mine** existing SQL/BI: query logs, dbt models, view definitions, BI field mappings (`SELECT text_2 AS customer_name` *is* documentation).
3. **LLM-draft** a description + synonyms + examples per physical column; **human-approve**; mark inferred mappings low-confidence until validated.
4. Store a **glossary** (`{physical, table, means, synonyms, examples, confidence, join_paths}`). Text-to-SQL retrieves over the **glossary**, never the raw schema; the model writes `SELECT text_2 FROM tbl_44` correctly because retrieved context told it what `text_2` means.
5. **Govern it**: ownership + CI that flags schema drift (new/renamed columns) so stale descriptions can't mislead.

This is its own subsystem (`enrichment/schema_glossary/`): a profiler + query-log miner + LLM-drafter + glossary store + drift check.

### 3.4 Offline build pipeline (no always-on machine, no GPU)

The expensive work is **build-time batch, not serve-time** — it runs on-demand when the corpus changes, then exits. With the chosen stack every step is an API call or light CPU work, so it runs on a laptop, titan-pc, or a **GitHub Actions runner** (`make index`):

| Build step | Engine / model | Compute |
|---|---|---|
| chunk corpus | Chonkie | CPU |
| embed chunks | **Voyage-3-large (API)** | network |
| contextual enrichment | **Groq / NVIDIA (API)** | network |
| build vector index → `index.tvq` | **TurboVec** (Rust/CPU SIMD) | CPU |
| profile values + draft glossary | DuckDB/Polars (CPU) + Groq/NVIDIA (API) | CPU + network |
| dedup (funnel) | datasketch MinHash | CPU |

**Artifact flow:** the batch writes chunk text + ACLs + graph + catalog + glossary into **SurrealDB Cloud** (managed, always-up) and emits the **TurboVec index as a file** (`index.tvq`, ≈384 B/vec → ~19 MB for 50k chunks). The index ships in the function bundle or **Vercel Blob**; the serverless function loads it on cold start. **Serving (per query) touches only hosted services** — Vercel + SurrealDB Cloud + Cohere rerank + Groq generate + BigQuery — so nothing of yours stays online. titan is *optional*: a convenient batch host, or a future home for local embeddings (TEI + bge-m3) / self-hosted stores if free tiers are outgrown.

### 3.5 The demo org & data story — "Meridian" (locked 2026-06-08)

Every dataset is justified by one fictional org, reverse-engineered to fit the real public sources so the demo *makes sense*.

**Meridian** — "the everything app for cities": a global **super-app + marketplace** (~12,000 employees, multi-region) running **ride-hailing/logistics**, an **online marketplace/retail** arm, **fintech/payments**, **ads/growth**, and a **corporate strategy** function. It grew by **acquisition** — which is *why* its warehouse has meaningless column names and its data sprawls across systems. A super-app is the one org type that naturally produces all of: trips, retail transactions, payments, ads, plus heavy external-signal monitoring — and it makes all three hero demos land (PB funnel over trips/sales; opaque-schema glossary over the acquired retailer's warehouse; need-to-know governance across Finance/HR/Legal/Security).

**Org structure → personas → clearance (0=public … 5=board):**

| Vertical | Owns | Personas (clearance) |
|---|---|---|
| Finance | revenue by segment, **pre-release financials** | Finance Manager (L4), CFO (L5) |
| People/HR | Workday HRIS, **exec comp**, headcount | HR Analyst (L2); comp visible only L5 |
| Sales | Salesforce pipeline, contracts, deal value | Sales Manager (L3) |
| Legal & Compliance | contracts, **M&A**, litigation | Legal Counsel (L4) |
| Engineering / Data Platform | the warehouse, runbooks, prod creds | Engineer (L2) |
| Mobility Ops | trip records, driver/rider PII | Ops Analyst (L2) |
| Marketplace/Commerce | sales transactions, merchant + customer data | Commerce Analyst (L2) |
| Marketing/Growth | campaigns, ad spend, market signals | Marketing Analyst (L2) |
| Risk & Security | incidents, threat intel, audit logs | CISO (L4) |
| Strategy/Intelligence | competitor filings, M&A targets | Strategist (L4) |
| Knowledge/Support | internal wiki, support threads | Support Agent (L1), Intern (L1) |

Gives a deliberately **non-monotonic** access matrix (Finance sees financials not comp; HR sees comp not financials; Legal sees neither; CEO/CFO see both) — what makes the leak audit non-trivial.

**Data estate — in-story asset → real public source → connector → vertical → sensitivity:**

| In-story asset | Real public source | Connector | Vertical | Clearance / masking |
|---|---|---|---|---|
| Marketplace transactions | **TPC-DS** `store_sales` | Warehouse | Commerce/Finance | `customer_email` masked; raw L3, aggregates L1 |
| Mobility trips (~1.6B rows) | **NYC TLC** (BigQuery public) | Data lake | Mobility Ops | pickup/dropoff coords masked (PII); aggregates L1 |
| Global events / risk signals | **GDELT** (BigQuery public) | Data-share | Strategy/Marketing | L1 |
| Web/competitor corpus | **Common Crawl** (AWS S3) | S3 object store | Strategy | **catalog-only** (PB tail), L1 |
| Company filings (due diligence) | **SEC EDGAR** | Files/API | Strategy/Legal | public L0 |
| Open city/economic data | **data.gov** | Files/API | Ops/Marketing | public L0 |
| Internal knowledge base | **Wikipedia/Wikimedia** dump | Confluence/wiki | Knowledge | L0–L1 (vector KB) |
| HR records + **exec comp** | *synthetic* (Workday) | HRIS | People | comp L5; policy L1 |
| CRM pipeline | *synthetic* (Salesforce) | CRM | Sales | field-level security on deal value |
| Internal comms | *synthetic* (Slack) | Messages | all | channel-scoped |
| **Pre-release financials** | *synthetic* (derived from TPC-DS aggregates) | Drive/warehouse | Finance | L5 |
| **M&A / litigation memos** | *synthetic* | Drive | Legal | L5 |

Where no true public dataset exists (HR comp, CRM, Slack, M&A), use **clearly-labeled synthetic** data — honest, and where the sharpest governance scenarios live.

**The narrative (what a visitor experiences):** Meridian is a super-app drowning in data — PB of trips/transactions in an acquired warehouse with meaningless column names, billions of event/web records too big to ingest, and sensitive HR/Finance/Legal material across Slack/Drive/Confluence/Salesforce/Workday. The visitor **picks a persona**, asks a question, and watches: router picks a backend → funnel collapses PB→thousands → text-to-SQL translates `text_2` via the glossary → retrieval → **governance drops what that persona can't see** → cited answer + audit trail. **Headline scene:** an **Intern** asks *"what are our Q3 projections and exec salaries?"* → restricted rows/chunks dropped + audited; the **CFO** asks the same and gets them. Same index, different session token.

---

## 4. Governance model (extended across backends)

- `SecurityContext` extends from chunks to **catalog assets** and **columns** (column-level masking, e.g. `ss_customer_email`, lake pickup coordinates, Salesforce field-level security).
- **At scale, enforcement moves from post-filter to index-level pre-filter** with late binding to the source-of-truth ACL — you cannot re-check every doc against an ACL service per query at PB scale.
- The **adversarial leak audit** (existing) extends to: every persona × every query × every backend × every admitted chunk/row/column = **0 leaks**, enforced as a CI gate. Masked columns must never reach unauthorized roles.
- **Provenance/citations** on every answer (TRANSPARENT pillar); audit trail per retrieval.

---

## 5. Pillar alignment (7 pillars — SOVEREIGN dropped for PROJECT-M)

> SOVEREIGN no longer applies under `~/project-m` (memory `project-m-drops-sovereign-pillar`). Offline-capability survives as an optional selling point, not a constraint.

- **SECURE** — RBAC into the index, parameterized/AST-validated SQL only (`sqlglot` read-only gate), column masking, leak audit as a CI gate, fine-grained authz via a ReBAC engine (Oso Cloud / OpenFGA).
- **TRANSPARENT** — citations + provenance + per-retrieval audit trail; OTel/OpenLLMetry → Langfuse tracing with per-request cost/token; the funnel exposes the retrieval path.
- **CONFIGURABLE** — backends/providers swap via env/injection; tunables centralized in `EngineConfig`; no magic numbers; cost guardrails (BigQuery `maximum_bytes_billed`, parse-mode, sampling) all config-driven.
- **ROBUST** — frozen Pydantic models, validators, deterministic router fast-path.
- **RESILIENT** — circuit breakers + bounded retries on external API calls (parse/embed/rerank/LLM), graceful degradation when a backend is down.
- **PERFORMANT / ELASTIC** — coarse-to-fine, TurboQuant 16× compression, partition pruning, semantic caching (roadmap).

---

## 6. What's built vs roadmap (PMB-style honesty for the public doc)

| Capability | Status |
|---|---|
| 5-layer offline engine, hybrid retrieve, governance post-filter, leak demo, eval gate, FastAPI | ✅ Built (bundle) |
| Unified multi-connector catalog + verticals + personas + Sources page | ⏳ This project |
| BigQuery text-to-SQL backend (NYC TLC, GDELT) + partition pruning + `maximum_bytes_billed` cost guard | ⏳ This project |
| Opaque-schema semantic glossary subsystem | ⏳ This project |
| SurrealDB unified store (graph + structured + full-text + catalog) + TurboVec compressed vector index | ⏳ This project |
| Funnel visual + scale math + provenance/scale badges | ⏳ This project |
| Index-level pre-filter governance (replacing post-filter at scale) | 🔭 Roadmap |
| Re-embedding/version-migration, CDC streaming ingestion, semantic cache | 🔭 Roadmap |
| Self-RAG / corrective grading, true agentic loop backend | 🔭 Roadmap |

---

## 7. Phase plan (high level — detailed steps come from `writing-plans`)

1. **P0.0 Repo readiness** — extracted ✅; add `docs/`, decide remote (Gitea private vs GitHub public — `git-remote-policy`).
2. **P0.1 Catalog core** — `catalog/` registry, `Connector` ABC, extend `SecurityContext` to assets/columns, verticals + personas, leak audit over the catalog.
3. **P0.2 SurrealDB unified store** — stand up SurrealDB (Cloud free / self-host); model catalog + `SecurityContext` + the four retrieval modes (vector via TurboVec TurboQuant index, graph edges, SurrealQL structured, full-text) behind the existing `Retriever`/`Backend` ABCs; router selects the retrieval mode.
4. **P0.3 External PB tail + text-to-SQL** — BigQuery connector (NYC TLC, GDELT) with partition pruning; Common Crawl catalog-only; the text-to-SQL agent; router learns indexable-derivative (SurrealDB) vs PB-tail (BigQuery) + prune.
5. **P0.4 Opaque-schema glossary** — profiler + query-log miner + LLM-drafter + glossary store (in SurrealDB) + drift CI; wire text-to-SQL to retrieve over the glossary, never the raw schema.
6. **P0.5 Funnel + observability** — funnel math, scale/provenance metadata, per-retrieval tracing.
7. **P0.6 Demo surface** — Sources + Pipeline + funnel pages (integrated into `portfolio_app` `/projects/clearance` per the Ledger spec); deploy.

Each phase ends with the leak audit green and the eval gate passing.

---

## 8. Decisions — RESOLVED 2026-06-08

- **TurboVec** ✅ (`github.com/RyanCodrai/turbovec`, MIT, Rust+PyO3, TurboQuant 16×) — the vector index, allowlist filtered search. Persist the index; load on cold start (≈384 B/vec keeps it small); revisit if cold-start latency hurts.
- **SurrealDB hosting** ✅ **Hybrid** — SurrealDB **Cloud free tier** (account already created) serves the live hosted demo path; **self-host on titan-pc** for dev, heavier corpora, and headroom. Same engine both sides; connection string is config (CONFIGURABLE).
- **External warehouse** ✅ **BigQuery** — public datasets (NYC TLC, GDELT) on the sandbox free tier; the text-to-SQL target for the PB tail.
- **Text-to-SQL safety** ✅ read-only credentials · `sqlglot` AST gate (reject any non-SELECT) + allow-listed/parameterized generation · `maximum_bytes_billed` + mandatory partition filter cost guard. (SECURE pillar.)
- **LLM provider** ✅ **Groq (default — LPU, sub-second) + NVIDIA NIM (alternate)**, both **OpenAI-compatible**, behind the existing `Generator` ABC (replaces Anthropic for the demo; user holds keys for both). Same provider used for generation, Contextual-Retrieval enrichment, glossary LLM-drafting, and the eval judge. Extractive generator stays the zero-dependency offline fallback. Provider/model are config (`RAG_GENERATOR`, base_url, model).
- **Secrets** ✅ connector + provider creds via Vercel env + `.env.local`, durable copy in **Vaultwarden** (`credentials-policy`). Never committed.
- **Remote/visibility** ✅ **both** — public **GitHub** (`github.com/rishav1305`, client-magnet) **and** private **Gitea** mirror. Push to both; verify with `git-remote-policy` before the first GitHub push.
- **Demo deploy** ✅ stateless orchestrator on **Vercel Python serverless (Hobby, $0)** behind `portfolio_app` `/projects/clearance`; replicate PMB's `maxDuration: 300` config. All stores hosted. **No always-on machine of yours is required** — heavy work is an *on-demand batch* (see §3.4): embedding is a Voyage API call, LLM steps are Groq/NVIDIA API, and the index/profiling/dedup are light CPU that runs on a laptop, titan-pc, or a GitHub Actions runner, then exits. Serving path = Vercel + SurrealDB Cloud + Groq/NVIDIA + BigQuery, all managed. Pro ($20) only if always-warm/commercial-ToS forces it later.
- **Licenses** — informational only (SOVEREIGN dropped). TurboVec MIT; SurrealDB BSL 1.1; Firecrawl AGPL; rest Apache/MIT. Not gating.

---

## 9. Tooling & dependency choices (researched 2026-06-08, verified live)

Principle: **adopt mature tools *around* the differentiators; keep the differentiators first-party.** SOVEREIGN is dropped, so managed/SaaS/paid-API options are in play where they win on quality or build-effort.

### Keep first-party (the moat — a library would dilute it)
- The permission-aware **drop-before-model enforcement** + **leak-test oracle** + **JSONL audit log/provenance**.
- The **5-layer ABC pipeline spine** (frameworks hide exactly the governance seam we must expose).
- **Custom RRF** (~15 lines, hot path) and the **text-to-SQL-over-glossary** orchestration (no off-the-shelf tool models "retrieve over the glossary, not the schema").

### Adopt
| Stage | Tool | Note |
|---|---|---|
| Connectors/ingestion | **dlt** (MIT) | in-process; loads into custom targets (SurrealDB/TurboVec). Optional Fivetran for hairy SaaS (Salesforce/Workday/Slack/Confluence) routed via a warehouse. |
| Doc parsing | **LlamaParse** default · **Reducto** for financial/legal/EDGAR · Docling for bulk | biggest quality win unlocked by dropping the license filter. Tiered by doc difficulty. |
| Web crawl | **Firecrawl** (API) + **Exa** for discovery | replaces crawl4ai (AGPL no longer a blocker). |
| Chunking + contextual | **Chonkie** (MIT) + **Contextual Retrieval** at ingest (via Groq/NVIDIA) | per-chunk context call now allowed (−67% retrieval failures w/ rerank); provider-agnostic — run on Groq/NVIDIA, not Anthropic. |
| LLM generation | **Groq** (default, LPU-fast) + **NVIDIA NIM** (alt), OpenAI-compatible, behind the `Generator` ABC | replaces Anthropic; generous free tiers; sub-second inference shrinks the request path; extractive stays offline fallback. |
| PII detection | **Presidio** (MIT) | hosted DLP can't see Slack/Salesforce/Workday; Presidio runs cross-source. Masking *policy* stays first-party. |
| Embeddings | **Voyage-3-large** | leads on technical/financial/legal retrieval. ⚠️ swap forces a full re-embed + TurboQuant recall re-validation — sequence as its own task. |
| Reranking | **Cohere Rerank 4 Pro** behind the **`rerankers`** abstraction | top commercial quality, no local GPU; `rerankers` keeps providers swappable. |
| Adaptive router | **semantic-router** (MIT, local) | replaces the brittle regex router; embedding-similarity routing, no LLM in hot path. |
| Text-to-SQL safety | **sqlglot** (MIT) | AST parse → reject non-SELECT, enforce limits, transpile to BigQuery dialect. |
| Glossary mining | **sqlglot.lineage**; glossary stored in **SurrealDB** | column-level lineage from query logs/views/dbt manifest; no separate catalog platform. |
| Big-data access | **google-cloud-bigquery** + **DuckDB/Polars** over `hf://`/`s3://` | query in place. |
| Dedup (funnel) | **datasketch** (MinHashLSH) + semantic 2nd pass via TurboVec embeddings | — |
| Eval / CI gate | **DeepEval** (pytest `assert_test`) + **RAGAS** metrics | keep the governance/leak assertions custom. Optional Braintrust for a hosted dashboard. |
| Red-team | **promptfoo** (CI gate) + **garak** (weekly) | ⚠️ promptfoo acquired by OpenAI (Mar 2026) — still MIT; minor governance note (we run non-OpenAI models on Groq/NVIDIA). |
| Authorization | **Oso Cloud** (managed `list-objects` → pre-filter set); SpiceDB self-host as the cheaper growth path | answers "which objects can user X see" to pre-filter retrieval. Keep drop-decision + audit first-party. |
| Observability | **Langfuse Cloud** via **OTel/OpenLLMetry** | per-request cost/token + retrieval-path spans; vendor-portable instrumentation. |

### Frameworks (the explicit question)
- **Backbone: keep the custom 5-layer ABC pipeline.** Do not adopt LangChain or LlamaIndex wholesale.
- **LangGraph** — only if/when the flow becomes genuinely agentic (loops / re-retrieval / HITL), as the orchestration layer *behind the router ABC*. PMB already uses it.
- **LlamaIndex** — à la carte library only (e.g. LlamaParse, a retriever), never owning the chunk/governance boundary.
- **LangSmith** — **not needed** (custom pipeline + Groq/NVIDIA OpenAI-compatible stack). OTel/OpenLLMetry → Langfuse is more portable and covers tracing + cost + provenance.

### To revisit
- **Text-to-SQL**: Vanna 2.0 un-archived; **Wren AI** maintained — both overlap the glossary. *1-day spike* on Wren's MDL; adopt only if it cleanly models opaque-schema retrieval at lower build cost. Default: keep the build.
- **Vector**: TurboVec stays the edge for this poly-store design. **Qdrant Cloud** is the fallback *only* if serverless-loading the index becomes impractical at corpus growth.

---

## 10. Platform setup & cost route (researched 2026-06-08, verified live)

**Headline: the demo runs ~$0/mo on Vercel Hobby** (PMB pattern — `maxDuration: 300`), with **indexing as an on-demand batch** (laptop / titan-pc / GitHub Actions) so nothing of yours stays online and the request path stays short. Every component lands on a real free tier; LLM inference is on Groq/NVIDIA free tiers. No Vercel Pro needed, no always-on machine, no GPU.

| Platform | Free tier | What drives cost | Demo route |
|---|---|---|---|
| **Vercel** (orchestrator) | Hobby ($0) — PMB runs `maxDuration: 300` here today | Active CPU-seconds | **$0 on Hobby**; indexing is an on-demand batch (not in the request). Pro ($20) only if always-warm/commercial-ToS forces it. |
| **SurrealDB** | Cloud free 0.25vCPU/512MB/1GB (account created) | always-on compute | **hybrid**: Cloud free for the hosted demo + self-host on titan-pc for dev/headroom ($0) |
| **TurboVec** | OSS in-function | function RAM | $0 always |
| **BigQuery** | Sandbox 1 TB scanned + 10 GB, no card | bytes scanned | $0 under partitioned/`LIMIT`-ed queries |
| **Common Crawl/S3** | public read | **egress ~$0.09/GB** | query in-region, sample only — never bulk-download |
| **LlamaParse** | 10k pages/mo | pages × mode | $0 at demo volume |
| **Firecrawl** | 1k credits/mo | pages crawled | $0 at demo volume |
| **Voyage** (embed) | 200M tokens lifetime | tokens embedded | $0 (demo corpus is a rounding error) |
| **Cohere Rerank** | trial 1k calls/mo (non-commercial) | search units | $0 demo; **first real $** at commercial (~$2/1k) |
| **Oso Cloud** | Dev free 100k req/mo | authz requests | $0 demo; $149 cliff → self-host SpiceDB to grow |
| **Langfuse** | Hobby 50k events/mo | events ingested | $0 demo; self-host on titan to grow |
| **LLM (Groq / NVIDIA)** | Groq + NVIDIA NIM free tiers (user holds keys) | tokens beyond free tier | **~$0 at demo volume**; Groq default for speed, NVIDIA NIM as alt/larger-model |
| **OSS toolbelt** | free | batch CPU (laptop/CI) | $0 always |

**Most cost-effective route:** Vercel **Hobby ($0)** · SurrealDB hybrid (Cloud free + optional titan) · TurboVec index as a shipped file ($0) · BigQuery sandbox · free tiers for parse/crawl/embed/rerank/authz/trace · **LLM on Groq/NVIDIA free tiers** · indexing as an on-demand batch (laptop / titan-pc / GitHub Actions — no always-on box).

**Monthly estimate:** **demo ≈ $0/mo.** **Light-production ≈ $250–400/mo** — the cliffs are Oso ($149 → self-host SpiceDB), LlamaParse page overflow, Cohere reranking at volume, and Groq/NVIDIA tokens past the free tier (still far cheaper than frontier APIs).

**Cost guardrails (all config-driven — CONFIGURABLE pillar):** BigQuery `maximum_bytes_billed` cap + mandatory partition filter + no `SELECT *`; `parse_mode=cost-effective` default with an agent-mode allowlist; incremental/content-hash embedding (never full re-embed in CI); `max_duration ≤ 300s` + run heavy compute (embedding, indexing, eval suites) as an on-demand batch off the request path; `trace_sampling_rate < 1.0` in prod; bounded crawl depth + retry budgets.

**For the 4-project portfolio:** free tiers + titan self-hosting amortize across all four; on Vercel Hobby the marginal platform cost of the whole portfolio is **~$0/mo**.

---

*Status 2026-06-08: engine extracted to `~/project-m/projects/enterprise-rag-engine/`. Spec covers architecture (SurrealDB hybrid + TurboVec + BigQuery PB tail), tooling (§9), and platform/cost (§10). §8 decisions RESOLVED: SurrealDB hybrid (account created), BigQuery, Groq+NVIDIA LLM (OpenAI-compatible), dual remote (GitHub + Gitea), Vercel Hobby ($0). SOVEREIGN dropped per project-m policy. Demo ≈ $0/mo. Next: user review, then `writing-plans` for P0.1.*

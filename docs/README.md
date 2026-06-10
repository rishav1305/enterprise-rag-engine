# CLEARANCE — Documentation

> **Poly-store, petabyte-scale, permission-aware enterprise RAG.**
> The one-line proof: **drop unauthorized content before it reaches the model — proven by a 210-cell leak oracle that fails CI on any leak.**

This is the top-level entry to the CLEARANCE documentation. It is structured **top-down**:
the exec summary is here; depth increases as you descend into `architecture/`.

| | |
|---|---|
| **Source spec** | [`superpowers/specs/2026-06-08-clearance-polystore-design.md`](superpowers/specs/2026-06-08-clearance-polystore-design.md) |
| **World bible** (the demo org + data estate) | [`meridian-org-and-data.md`](meridian-org-and-data.md) |
| **Architecture deep dives** | [`architecture/`](architecture/) |
| **Ops / runbook** | [`architecture/12-ops-runbook.md`](architecture/12-ops-runbook.md) |

---

## 1. What CLEARANCE is (the headline)

Enterprise RAG is not a product category, and the retrieval algorithm is the commoditized
30%. The moat is the **70% everyone skips**: messy multi-vertical data integration, a
permission model that travels *into the index*, provenance/citations, freshness, and
evaluation. CLEARANCE is built around that 70%.

**The headline claim** — *"I can manage petabytes and run RAG over them across all five
layers"* — is demonstrated honestly:

- You never embed a petabyte. You build the **funnel** that turns PB of raw enterprise data
  into the ~thousands of candidates a single query actually touches.
- You route each query to the **right backend** (vector / warehouse text-to-SQL / graph /
  lexical) over the **right partition**.
- You **drop unauthorized content before it can ever reach the model** — and prove it with an
  adversarial leak test that **fails CI on any leak**.

### The visible proof: the persona switcher

The demo (`src/app/projects/clearance` in `portfolio_app`, backed by this engine's FastAPI
`api.py`) sends the **same question** as four personas — **Intern (L1) / Data Analyst (L2) /
Finance Manager (L4) / CFO (L5)** — and returns **different governed answers** side by side.
The difference is the session's clearance, *not* the index. The UI shows a `n_withheld` count
("🔒 N items withheld for your clearance") — governance made legible **without disclosing what
was withheld** (the ACL trail is operator-only, audit-side; see [§11 demo](architecture/11-demo-and-deploy-security.md)).

### The credibility artifact: the leak oracle

`tests/test_leak_oracle.py` + `tests/test_oracle_parity.py` run a **210-cell oracle**
(15 personas × 14 sensitivity classes A–N) on every commit. Any single cell that leaks fails
`make ci`. The engine **cannot ship with a known leak**. P0.11a extended this end-to-end
through the fully-wired pipeline (`tests/test_e2e_fully_wired_leak_oracle.py`).

---

## 2. Architecture at a glance

CLEARANCE is a **pure-Python engine with five swappable ABC layers** (each backend is
env-selectable, no code change), plus Generation / Eval / Service. It runs **offline with zero
model downloads** by default; managed/SaaS backends are optional drop-ins.

```
query + Session
      │
      ▼  L3 ROUTING            routing/heuristic_router.py — complexity + retrieval-mode + partition
      ▼  L4 RETRIEVAL          retrieval/ — vector (TurboVec) + the 3 pre-filtered modes (graph/structured/lexical)
      │      └─ ALLOWLIST PRE-FILTER (stage 1): an unauthorized chunk is never a candidate (drop-before-search)
      ▼  L5 GOVERNANCE         governance/ — SecurityFilter.apply (stage 2): redact mask/partial, drop deny, audit
      ▼  Generation            generation/ — extractive (offline) | Claude/Groq/NVIDIA (gated)
      ▼  RAGResponse           answer + governed citations + governance trail (operator) / n_withheld (client)
```

### The poly-store (one governed catalog over many backends)

| Store | Role | Module |
|---|---|---|
| **SurrealDB** (multi-model) | unified system of record: chunk text + ACLs + catalog + glossary + graph edges + structured + full-text | `store/surreal.py`, `store/schema.py` |
| **TurboVec** (compressed vector index) | the vector ANN, with the **allowlist permission pre-filter at the index** | `retrieval/turbovec_index.py`, `turbovec_retriever.py` |
| **BigQuery** (PB tail, query-in-place) | warehouse text-to-SQL over the true-petabyte tail (NYC-TLC, GDELT) — never bulk-ingested | `connectors/bigquery.py`, `texttosql/` |

### The two-stage governance model (defense in depth)

1. **Allowlist PRE-filter (drop-before-search)** — `governance/allowlist.py`. The set of chunk
   ids a session may retrieve (decision ≠ `deny`) is handed to the index, so an unauthorized
   item is **never even a candidate**. Applies to vector AND the graph/structured/lexical modes
   (P0.6). The allowlist engine is swappable (`AllowlistBackend`: in-process default, or ReBAC
   SpiceDB/Oso — parity-guaranteed to the in-process decision).
2. **L5 SecurityFilter post-filter (redact)** — `governance/filter.py`. At the retrieval
   chokepoint, each chunk's decision is re-evaluated: `deny` dropped, `mask`/`partial` **redacted**
   (`governance/masking.py` → `[REDACTED]`), `allow` passes. The audit trail records every
   decision (TRANSPARENT).

Every component that consumes retrieved chunks **outside** the pipeline — the semantic cache,
the corrective loop — **self-applies both stages** (the loop self-redacts; the cache re-governs
on hit). This is why a standalone-safe component can't leak once composed; the
`test_e2e_fully_wired_leak_oracle` master gate proves it.

---

## 3. What's wired-live vs. built-standalone (honest framing)

Most subsystems were built + hardened standalone (with their own governance proofs), then wired
into `RAGPipeline.query` as **optional injected collaborators** in P0.11a. The decomposition
([`superpowers/plans/2026-06-08-p0-decomposition.md`](superpowers/plans/2026-06-08-p0-decomposition.md))
tracks the remaining integration follow-ons honestly — chiefly the **live external connectors**
(SurrealDB Cloud, Groq/NVIDIA LLM, Voyage embeddings, BigQuery, Langfuse, SpiceDB/Oso) which are
**creds-gated** in tests (faked deterministically locally) and enforced live only with credentials.
See each deep dive's "wired-live vs gated" note.

---

## Deep-dive index

| # | Subsystem | Doc |
|---|---|---|
| 1 | Data & seeds (Meridian, 15×14 matrix, opaque legacy_mart) | [`architecture/01-data-and-seeds.md`](architecture/01-data-and-seeds.md) |
| 2 | Catalog + SecurityContext | [`architecture/02-catalog-and-security-context.md`](architecture/02-catalog-and-security-context.md) |
| 3 | Governance (access.evaluate, the leak oracle) | [`architecture/03-governance.md`](architecture/03-governance.md) |
| 4 | Store + TurboVec | [`architecture/04-store-and-turbovec.md`](architecture/04-store-and-turbovec.md) |
| 5 | Retrieval (vector + 3 pre-filtered modes) | [`architecture/05-retrieval.md`](architecture/05-retrieval.md) |
| 6 | SQL-safety + text-to-SQL result masking | [`architecture/06-sql-safety-and-text-to-sql.md`](architecture/06-sql-safety-and-text-to-sql.md) |
| 7 | Opaque-schema glossary | [`architecture/07-glossary.md`](architecture/07-glossary.md) |
| 8 | Funnel + observability | [`architecture/08-funnel-and-observability.md`](architecture/08-funnel-and-observability.md) |
| 9 | Semantic cache (scope key + re-govern) | [`architecture/09-semantic-cache.md`](architecture/09-semantic-cache.md) |
| 10 | Self-RAG / corrective loop | [`architecture/10-self-rag-loop.md`](architecture/10-self-rag-loop.md) |
| — | CDC / re-embedding | [`architecture/10b-cdc-and-reembedding.md`](architecture/10b-cdc-and-reembedding.md) |
| — | Multimodal | [`architecture/10c-multimodal.md`](architecture/10c-multimodal.md) |
| 11 | Demo API + Gate A/B deploy-security | [`architecture/11-demo-and-deploy-security.md`](architecture/11-demo-and-deploy-security.md) |
| 12 | Ops / runbook | [`architecture/12-ops-runbook.md`](architecture/12-ops-runbook.md) |

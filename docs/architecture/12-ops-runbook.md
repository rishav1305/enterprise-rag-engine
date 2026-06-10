# 12 — Ops / runbook

## The CI gate (`make ci`)

`scripts/ci.sh` is THE local pre-merge gate — and the headline credibility artifact (the leak
oracle runs here). It is **0-skip**: a silently-skipped governance test is a false green.

```
make ci      # RAG_DEV_ENV=1; requires the surreal binary + pinned dev deps; 0 skips
```

What it does:
1. **enforce the dev env** (`RAG_DEV_ENV=1`) — turns `importorskip`/`skipif` guards into hard
   failures (a missing turbovec/surreal in CI fails loudly, not silently);
2. **dep-guard preflight** — assert the pinned dev deps are importable;
3. `pytest -m "not cloud and not bq and not llm and not langfuse and not spicedb and not oso"` —
   the creds-gated markers are **deselected** (not skipped) so the local/offline suite is complete;
4. a **no-skip headline assertion** — a curated list of governance/oracle/retrieval/store tests
   must run, not skip (belt-and-suspenders against a false green);
5. `ruff` lint.

The **210-cell leak oracle** + every phase's governance suite (allowlist parity, cache permission,
selfrag governance, CDC reclassify, multimodal governance, the HTTP governance + deploy guards, and
the master end-to-end oracle) are all in that gate. **Interpreter:** `PYTHON ?= python3` (override
with `PYTHON=…`); the surreal binary at `~/.surrealdb/surreal` (add to `PATH`).

Other Makefile targets: `make demo` (the INTERN-vs-CFO leak demo), `make seed` (generate the
Meridian estate), `make api` (serve FastAPI at :8000), `make dev` (editable install + dev deps).

## Configuration (the CONFIGURABLE pillar)

All tunables live in `config.py::EngineConfig` — env-overridable, schema-validated at construction
(`__post_init__` **refuses to start** on an invalid value, never a silent default). Key groups:

- **retrieval:** `embedding_dim`, `vector_coarse_k`, `final_top_k`, `rerank_top_k`, RRF/`dense_top_k`;
- **warehouse:** `bq_max_bytes_billed` (cost cap), `bq_require_partition_filter`, `bq_dialect`;
- **routing/text-to-SQL:** `router_backend`, `sql_generator`, `sql_llm_base_url`/`model`, `glossary_drafter`;
- **store:** `store_backend` (memory|surrealdb), `surreal_dsn`/`ns`/`db`/`user`/`pass`;
- **cache (P0.7):** `cache_enabled`, `cache_similarity_threshold`, `cache_ttl_seconds`, `cache_max_entries`, `cache_backend`;
- **self-RAG (P0.8):** `selfrag_enabled`, `selfrag_max_iterations`, `selfrag_relevance_threshold`, `selfrag_groundedness_threshold`, `selfrag_grader`;
- **allowlist (P0.11a):** `allowlist_backend` (in_process|local_rebac|spicedb|oso);
- **CDC / multimodal:** `embedder_version`, `multimodal_max_payload_bytes`;
- **deploy-security (P0.11b):** `rate_limit_per_min`, `instance_rate_limit_per_min`, `query_cap_per_day`, `demo_profile` (synthetic|production).

The full secret inventory is in [`docs/superpowers/DEPLOY_ENV_SCHEMA.md`](../superpowers/DEPLOY_ENV_SCHEMA.md).

## Multi-setup (hosted ⟷ self-host)

CLEARANCE runs **offline with zero model downloads** by default (deterministic `HashingEmbedder`,
extractive generator, in-memory store/cache). Every external dependency is a swappable backend
behind an ABC, creds/binary-gated:

| Capability | Hosted (managed/SaaS) | Self-host |
|---|---|---|
| Embeddings | Voyage | TEI / sentence-transformers / `HashingEmbedder` (offline) |
| LLM (generation, grader, SQL draft) | Groq / NVIDIA NIM / Anthropic | Ollama / extractive (offline) |
| Store | SurrealDB Cloud | SurrealDB self-host (the `surreal` binary) |
| Reranker | Cohere | cross-encoder (local) |
| ReBAC allowlist | Oso Cloud / SpiceDB Cloud | SpiceDB self-host / `LocalReBAC` (zero-dep) / in-process |
| Tracing | Langfuse | OpenTelemetry collector / in-memory |

Only DSN/creds differ — the same code path serves both (validated by the `surreal_local` ephemeral
fixture for CI and the gated `cloud`/`llm`/`bq`/`langfuse`/`spicedb`/`oso` markers for live).

## Deploy (go-live)

The demo deploy MUST use `demo_profile=synthetic`. The **three Gate B operational checks hard-block
public go-live** (deep dive [§11](11-demo-and-deploy-security.md)):

1. **rate-limit** (per-key + instance-wide) active;
2. **synthetic-only refuse-to-start** (no real source reachable);
3. **client-bundle no-secrets scan** passing (no secret-shaped string, no `NEXT_PUBLIC_*`
   credential).

> **TODO (filled after P0.11c live deploy):**
> - **Backend host:** `<TBD — CEO infrastructure decision pending>` (FastAPI + the synthetic
>   Meridian corpus; the FE's `CLEARANCE_API_URL` points here).
> - **Public demo URL:** `https://rishavchatterjee.com/projects/clearance` (frontend; Vercel —
>   note `portfolio_app` auto-deploys `main` → prod, so the clearance route ships on a branch
>   until go-ahead).
> - **Deployed API base URL:** `<TBD>`.

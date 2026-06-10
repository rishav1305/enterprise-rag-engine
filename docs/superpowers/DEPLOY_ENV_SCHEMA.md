# CLEARANCE demo — env-var / secret SCHEMA (P0.11b B0)

The Gate A endpoint inventory + which config is a SECRET (server-only) vs public.

## Backend (FastAPI, server-side only — NEVER in the browser bundle)
| Env var | Secret? | Purpose | Demo default |
|---|---|---|---|
| `RAG_CORPUS_DIR` | no | synthetic Meridian corpus path | bundled `corpus/` |
| `RAG_STORE_BACKEND` | no | `memory` (demo) \| `surrealdb` | `memory` |
| `SURREAL_DSN`/`SURREAL_USER`/`SURREAL_PASS` | **YES** | SurrealDB Cloud (if used) | unset (memory) |
| `RAG_SQL_LLM_API_KEY` / `GROQ_API_KEY` | **YES** | Groq/NVIDIA LLM | unset (fake gen) |
| `VOYAGE_API_KEY` | **YES** | live embeddings | unset (HashingEmbedder) |
| `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` | **YES** | trace export | unset (in-mem tracer) |
| `RAG_DEMO_PROFILE` | no | `synthetic` (refuse-to-start if a non-synthetic source is set) | `synthetic` |
| `RAG_RATE_LIMIT_PER_MIN` / `RAG_QUERY_CAP_PER_DAY` | no | per-KEY abuse caps (B-cap) | set in prod |
| `RAG_INSTANCE_RATE_LIMIT_PER_MIN` | no | INSTANCE-WIDE cap (closes X-User-Id rotation bypass of the per-key cap) | set in prod |

> **Edge note:** the per-key cap is bypassable by rotating `X-User-Id`; the instance-wide cap closes that at the app. For the PUBLIC demo URL, ALSO front it with **Cloudflare edge rate-limiting** (per-IP) — the synthetic profile already removes the run-up-bills risk (offline extractive generator, no live LLM creds), so the residual is compute-DoS, which edge rate-limiting handles best.

## Frontend (Next.js, portfolio_app — public bundle)
ZERO credentials. NO `NEXT_PUBLIC_*` secret. Only `NEXT_PUBLIC_API_BASE_URL` (the public
FastAPI URL — not a secret). Enforced by the B6 client-bundle no-secrets scan.

## Gate A endpoint inventory (the leak-coverage checklist)
| Endpoint | Demo feature | Gate A e2e leak test |
|---|---|---|
| `POST /query` | persona switcher, provenance, cost/token | ✅ B1 `test_api_http_governance` (HTTP TestClient; intern can't retrieve restricted; no body self-escalation) — mutation-proven |
| `GET /health` | liveness | n/a (no content) |
| `GET /personas` (new) | switcher options | B2 — read-only metadata, no restricted content |
| `POST /warehouse` | governed SQL masking | **NOT EXPOSED** — the demo headline is the persona switcher over /query; the warehouse SQL path is proven at the pipeline level (query_warehouse, deny short-circuit) but is NOT given an HTTP endpoint, minimizing the public attack surface per Gate A. If a future demo exposes it, it ships WITH a biting HTTP e2e leak test (deny→no-rows). |
| `GET /glossary` (new) | text_2→"customer name" | B4 — opaque mapping only, no row data |
| `GET /funnel` (new) | PB→TB→GB | B5 — stated scale numbers only |

# Adaptive Enterprise RAG — Permission-Aware Governance

> Most enterprise RAG failures aren't model failures. They're **governance, freshness, lineage, and evaluation** failures — the unglamorous 70%. This repo is built around that 70%.

A modular, production-shaped Retrieval-Augmented Generation engine that treats **access control as a first-class retrieval concern**. It demonstrates the engineering an enterprise operations team actually cares about: a document a user isn't cleared for is *retrievable* (so search quality is honest) but is **dropped before it can ever reach the model** — proven by an adversarial test that fails the CI build on any leak.

[![ci](https://img.shields.io/badge/ci-tests%20%2B%20governance%20gate-success)](.github/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![runs offline](https://img.shields.io/badge/runs-offline%20%7C%20zero%20model%20downloads-orange)](#quickstart)

---

## The headline: an adversarial leak that gets blocked

A low-privilege **INTERN** asks a question engineered to pull restricted data:

> *"What are our upcoming financial projections and current executive salary structures?"*

```text
SESSION  user=intern-1  roles=['INTERN']  L1
router selected: advanced_hybrid
retrieved=5  admitted=3  blocked=2

Governance trail:
  ✗ DROP   hr-exec-comp-2026  insufficient_clearance (session L1 < required L5)
  ✗ DROP   fin-q3-2026        insufficient_clearance (session L1 < required L4)
  ✓ ALLOW  pol-remote-2026    public_content
  ✓ ALLOW  prod-pricing-2026  public_content

Answer: ...home-office stipend of $500 ... (Grounded in: Remote Work Policy, Pricing Guide)
```

The same query as an authorised **CFO** returns the restricted figures. The
difference is the session token — not the index. That's the point: **retrieval
is permission-blind; enforcement is explicit and audited.**

Run it yourself: `make demo`

---

## Architecture — a swappable interface engine

Every layer is an Abstract Base Class. No hardcoded endpoints; backends swap via
env var or constructor injection without touching the pipeline.

```
            ┌─────────────────────────── INDEXING (once) ───────────────────────────┐
 corpus ─►  │ L1 Ingestion        L2 Enrichment                    L4 Index          │
            │ parse + extract ──► contextual anchors ──────────►   BM25 + dense      │
            │ RBAC (Pydantic)     (Anthropic Contextual Retrieval) (hashing/Qdrant)  │
            └────────────────────────────────────────────────────────────────────────┘

            ┌──────────────────────────── QUERY (per request) ──────────────────────┐
 query  ─►  │ L3 Router ─► L4 Hybrid Retrieve ─► L5 GOVERNANCE ─► Generation         │
            │ complexity   BM25 ∥ dense → RRF     drop unauthorised   answer from     │
            │ classifier   → rerank               chunks + audit      admitted only   │
            └────────────────────────────────────────────────────────────────────────┘
                                                  ▲
                                       session token (roles, clearance)
```

| Layer | Default (runs offline) | Production swap | Seam |
|---|---|---|---|
| **L1 Ingestion** | `MarkdownLoader` (YAML-frontmatter RBAC) | SharePoint / Confluence / S3 | `DocumentLoader` |
| **L2 Enrichment** | `LocalHeuristicContextualizer` | `AnthropicContextualizer` (prompt-cached) | `Contextualizer` |
| **L3 Routing** | `HeuristicRouter` (regex/keyword gate) | fine-tuned intent classifier | `QueryRouter` |
| **L4 Retrieval** | `HashingEmbedder` + `InMemoryVectorStore` | sentence-transformers + `QdrantVectorStore` | `Embedder` / `VectorStore` |
| **L4 Rerank** | `LexicalOverlapReranker` | `CrossEncoderReranker` (bge / Cohere) | `Reranker` |
| **L5 Generation** | `ExtractiveGenerator` | `AnthropicGenerator` (context-bound) | `Generator` |

The defaults are deliberate: the whole engine runs deterministically with **zero
model downloads and no GPU**, so CI and a reviewer's laptop both reproduce the
exact governance behaviour. Flip any backend on with one environment variable.

---

## Quickstart

```bash
pip install -r requirements.txt        # pure-Python, ~10s

make demo        # adversarial leakage walk-through (INTERN vs CFO) + eval gate
make test        # 21 tests incl. 5 adversarial leakage assertions
make api         # FastAPI at http://localhost:8000  (see /docs)
```

Query the API with an identity supplied in headers (server-derived, never
trusted from the body):

```bash
curl -s localhost:8000/query \
  -H 'X-User-Id: intern-1' -H 'X-User-Roles: INTERN' -H 'X-Clearance: 1' \
  -H 'content-type: application/json' \
  -d '{"question":"What are the Q3 financial projections?"}' | jq
```

### Enable the production backends

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export RAG_CONTEXTUALIZER=anthropic   # real Contextual Retrieval anchors
export RAG_GENERATOR=anthropic        # Claude, hard-bound to admitted context
docker compose --profile full up      # adds Qdrant + Redis
```

---

## The five layers in detail

**L1 — Ingestion & permission extraction.** Documents carry their ACLs in
frontmatter (`allowed_roles`, `clearance_level`, `owner_department`). The loader
**refuses to ingest un-governed content** and every chunk inherits its parent's
`SecurityContext` — a frozen Pydantic model. Security metadata is a constraint at
the point of ingestion, not an afterthought.

**L2 — Contextual enrichment.** Implements Anthropic's *Contextual Retrieval*
pattern: each chunk gets a one-sentence anchor situating it in the parent
document, which lifts both lexical and semantic recall. The Anthropic backend
caches the whole-document prefix across chunks to keep cost down.

**L3 — Adaptive routing.** A transparent complexity gate maps queries to a
strategy (`ADVANCED_HYBRID` for single-hop facts, `GRAPH_RAG` for relationship
questions, `AGENTIC_LOOP` for multi-hop reasoning) **before** touching the
clusters — protecting token budget and latency SLAs. Cheap, testable, no model
call to decide which model to call.

**L4 — Hybrid retrieval + RRF.** BM25 (exact codes, SKUs, proper nouns) and a
dense encoder (semantics) run in parallel, merge via **Reciprocal Rank Fusion**
(rank-based, so it sidesteps the BM25-vs-cosine score-scale mismatch), then the
top candidates pass through a reranker.

**L5 — Permission-aware verification & citations.** The chokepoint. Each
retrieved chunk is checked against the session (clearance **and** role, fail-closed);
unauthorised chunks are dropped **before generation**, so the model physically
cannot leak them. Admitted chunks become structured citations with immutable
SHA-256 content hashes, and every decision is written to an append-only audit log.

---

## Testing the enterprise vulnerability

`tests/test_data_leakage.py` constructs the attack and asserts three hard facts:

1. **Retrieval found it** — the hybrid index genuinely surfaced the restricted
   docs (so the test isn't vacuously passing by retrieving nothing).
2. **Governance blocked it** — every restricted chunk was denied and never
   entered the answer context for the INTERN.
3. **The answer is safe** — no restricted figure appears; a **CFO negative
   control** confirms the data *is* returned to an authorised caller.

The CI workflow runs this plus a quality gate with **zero tolerance for leaks**
(`max_leak_rate = 0.0`) and a recall floor — a PR that regresses either cannot merge.

---

## Why this exists

When a prospect opens this repo they don't see a neat trick; they see the precise
engineering friction enterprise teams pay for: **security boundaries that hold,
cost control via routing, lineage via hash-chained citations, and evaluation
wired into CI.** It's a reference implementation of doing the unglamorous 70% right.

## License
MIT — see [LICENSE](LICENSE).

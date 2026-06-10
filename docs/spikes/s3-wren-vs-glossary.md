# Spike S3 — Wren-AI MDL vs build the glossary (decision: BUILD)

**Date:** 2026-06-09 · **Owner:** Shuri · **Type:** timeboxed assessment (no code) · **Status:** ✅ KEEP THE BUILD (spec default) — Wren's MDL does not cleanly subsume the opaque-schema glossary at lower build cost

> **Question:** Does Wren AI's MDL (Modeling Definition Language) cleanly model opaque-schema retrieval (`text_2` → "customer name") at lower build cost than our own glossary subsystem — enough to adopt it instead of building?

## 1. What we need (the differentiator, spec §3.3)
A subsystem over the acquired `OldMart` warehouse (`legacy_mart`) whose columns carry NO semantic signal (`tbl_44`, `text_2`):
1. **Per-table semantics** — the *same* physical name means different things per table: `tbl_44.text_2` = full_name (masked PII), `tbl_71.text_2` = order_status (not PII). This is non-negotiable and already modeled in our estate (`seeds/synthetic/legacy_mart.GLOSSARY_TRUTH` + per-table masking from P0.2d).
2. **Profiler + view/query-log miner** (a legacy `CREATE VIEW v_cust AS SELECT text_2 AS name` is evidence).
3. **LLM-drafter** behind our `Generator` ABC (Groq/NVIDIA) with a deterministic fake for tests.
4. **Governed** — ownership, confidence flag (low until validated), drift CI, glossary stored in **SurrealDB**, masking respects per-table semantics.
5. **Deterministic, local, no-creds tests** (the whole repo's discipline).

## 2. Wren AI assessment
- **MDL** adds models/columns/relationships/views/metrics + RLAC/CLAC on top of an existing schema. It is built to **add business context to schemas that already have meaning**, not to reverse-engineer a meaningless one — the docs do **not** confirm the two decisive features: (a) `text_2`→"customer name" inference, (b) **per-table** disambiguation of an identical physical name.
- **Deployment:** a heavy stack — Apache DataFusion semantic engine (Rust), LanceDB memory, agent-native (LangChain) integrations, service/CLI-first. **Not a clean embeddable Python library:** `pip download wren-ai` / `wrenai` → *no matching distribution* (it ships as a docker/service deployment, not an importable lib).
- **Providers:** agent framework + (typically) cloud LLM/embedding — i.e. it would pull a creds-dependent service into the hot path, against our local/no-creds test discipline.

## 3. Why BUILD (not adopt)
| Requirement | Our build | Wren MDL |
|---|---|---|
| `text_2` → meaning inference | profiler + miner + LLM-drafter (purpose-built) | not its design (context over known schemas) |
| **Per-table** same-name semantics | ✅ already modeled (`GLOSSARY_TRUTH` + per-table masking) | unconfirmed in MDL |
| Embeddable, no service | first-party module in `enrichment/schema_glossary/` | docker/service stack, not a pip lib |
| Deterministic local/no-creds tests | fake LLM + fixtures | cloud-dependent agent stack |
| Stored in SurrealDB, governed, drift CI | native to our store + governance | separate catalog platform |
| Build cost | a profiler + sqlglot-lineage miner + a thin drafter + a glossary store (we already have sqlglot, the Generator ABC, SurrealDB, the estate truth) | integrate + operate a heavy external service for less fit |

The moat is *"retrieve over the glossary, not the raw schema"* with per-table governance — exactly the seam a framework hides. Adopting Wren would add operational weight (a service), a creds-dependent hot path, and an unconfirmed fit on the two features that matter, for **more** integration cost than building the focused subsystem on tools we already have.

## 4. Verdict — ✅ BUILD (spec default holds)
Keep the first-party glossary subsystem (`enrichment/schema_glossary/`): profiler + sqlglot-lineage view/query-log miner + Generator-ABC LLM-drafter (fake for tests) + SurrealDB glossary store + drift CI, respecting per-table semantics. Wren AI is a fine product for adding context to *known* warehouses; it does not subsume the opaque-schema, per-table, embeddable, no-creds-testable requirement at lower cost. Revisit only if Wren ships an embeddable lib that demonstrably infers per-table opaque-column meanings.

*Spike complete. Feeds P0.4: build the glossary subsystem first-party.*

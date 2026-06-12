# CLEARANCE Glass-Box UI — Design Spec

**Date:** 2026-06-12
**Status:** Approved (brainstorming) → ready for implementation plan
**Repos touched:** `enterprise-rag-engine` (backend + corpus + tests), `portfolio_app` (the `/projects/clearance` frontend)

---

## 1. Goal & thesis

Replace the current persona-card demo (`rishavchatterjee.com/projects/clearance`) with a transparent **glass-box audit console** that makes the governance **visible and un-fakeable** by exposing the engine's *real* per-query trace. The CEO's critique of the current UI: "anyone can fake it" — canned-looking answer cards prove nothing. The new UI proves governance by showing the actual pipeline dissect the question, transform it step by step, and drop/mask content *before the model* — with every number sourced from the engine, not hand-authored.

**Framing decision: auditor / observer.** The viewer is an auditor watching the engine govern a chosen persona's query. The auditor sees the *full* trace (including what was dropped/masked for the persona and why); the persona's own answer view stays redacted. This resolves the tension between "show the governance dropping content" and our own "denied users learn nothing" rule — the auditor is privileged; the persona is not.

## 2. Scope

**In scope:**
- Frontend redesign into 4 tabs: **Ask & Trace · Datasets · Leak Oracle · Architecture** (no login).
- A new backend audit endpoint `POST /trace` returning the full structured real trace, plus a catalog endpoint for the Datasets tab.
- A small **corpus enrichment** (~2 synthetic docs) so the live trace exhibits all four governance behaviors (allow / mask / partial / deny), not just allow/deny.

**Out of scope (explicit follow-ons):**
- Real external data connectors — the petabyte sources stay **catalog-metadata / query-in-place** (we show scale + provenance, not bulk data).
- SSE/true-live streaming — we use **fetch-the-real-trace + animated playback** (decided in brainstorming; robust on the free serverless stack).
- Auth/login — the demo trust model is "headers ARE the entitlement," unchanged.

## 3. Architecture overview

```
Browser (portfolio_app /projects/clearance, 4 tabs)
   │  ask + clearance lens
   ▼  POST /api/clearance/trace   (Next route-handler proxy, server-side CLEARANCE_API_URL)
Render backend (enterprise-rag-engine FastAPI, synthetic-only profile)
   │  POST /trace  → runs the REAL pipeline, instrumented, returns the full structured Trace
   ▼
Browser playback engine animates the Trace stage-by-stage (real per-stage timings)
```

The trace data already exists internally — the funnel (stage counts), `access.evaluate` (per-chunk decisions), the governance trail, the tracer spans (real durations), the retriever candidate sets + scores, the corrective-loop grades, and citations. The `/trace` endpoint **assembles** these into one structured response; it does not invent new behavior.

## 4. Backend — `POST /trace` (the audit endpoint)

**New endpoint** in `src/rag_engine/api.py`, model in a new `src/rag_engine/trace.py` (assembler) reusing the existing pipeline.

- **Input:** `{ question: str, roles: str, clearance: int }` (same header-derived session model as `/query`; clearance clamped [0,5]).
- **Guard:** runs **only under the synthetic profile** (`assert_synthetic_only` already enforced at startup → no real PII can ever appear in a trace). Same rate-limit guard as `/query`.
- **Output — a `Trace` object:**
  - `query_dissection`: `{ raw, key_terms[], embedding_preview (first 8 dims + "·512"), intent_shape, detected_topic }` — from the tokenizer + embedder + router classification.
  - `stages[]` — ordered, one per live stage (Routing, Retrieval, Governance, Generation; plus Identity/Guards, Memory/Cache, Response as lighter stages), each:
    - `id, layer, label`
    - `takes, does, pushes_out` — three short strings (the spine).
    - `duration_ms` — from the tracer span (real).
    - `status` — ok / warn.
    - `substeps[]` — the real sub-operations (e.g. Retrieval: embed → dense → lexical → RRF-fuse → rerank), each `{ label, io_label, ok }`.
    - `drilldown` — stage-specific raw data (see below).
  - `governance` (auditor-visible): per-candidate `{ title, decision (allow|mask|partial|deny), gate_fired, reason, required_level, required_roles }`. Drives the gate-by-gate drill-down + the allow/mask/deny bar.
  - `result` (the persona's governed view): `{ answer, citations: [{ title, doc_hash, quote }], admitted, n_withheld, access_denied }`.
- **Drill-down data per stage** (all real):
  - Retrieval → candidate list with dense scores + final rank.
  - Governance → the 4-gate evaluation order per candidate (public? → class-D PII? → level gate → need-to-know → legacy allowed_roles), marking which gate fired.
  - Generation → the corrective-loop iteration grades (relevance, groundedness) + stop_reason, and citation `doc_hash`es.
- **Parity invariant:** the per-candidate decisions in `trace.governance` MUST equal `access.evaluate(chunk, session)` for the same session — a test asserts the trace cannot drift from the real engine (this is what makes it un-fakeable).
- **Boundary safety:** the un-redacted trace is reachable **only** via `/trace` (the explicit auditor/demo endpoint, synthetic data only). The persona-facing `POST /query` stays **redacted** — `ClientRAGResponse`, no `governance_trail` (the ACL-disclosure fix shipped earlier) — **unchanged**.

## 5. Backend — catalog endpoint for the Datasets tab

**New `GET /trace/catalog`** returns the full estate: each of the 23 sources `{ name, type (synthetic-doc | real-public | warehouse-PB-tail | opaque-schema), scale_badge, sensitivity_class (A–N), clearance_level, provenance_url, live_queryable: bool }`, sourced from the catalog (`src/rag_engine/catalog/`) + `seeds/real/sources.py` + the synthetic source metadata. The 4 live demo docs are flagged `live_queryable=true`; the 7 real public + 16 synthetic + `legacy_mart` are `live_queryable=false` (catalog/provenance-only). The opaque-schema glossary mapping is included (already served by `/glossary`).

## 6. Backend — corpus enrichment (for live mask/partial)

The live demo corpus is currently **4 markdown docs** (pricing class A, remote policy class A/B, Q3 financials class E/L4, exec-comp class F/L5) — these only trigger **allow** and **deny**. To make the trace show **mask** and **partial** truthfully (live, not illustrated):
- Add **1 class-D customer-PII doc** (e.g. "Customer Account — sample") → masked at L2–L3, raw at L4+ (exercises `decision=mask`, `redact_chunk` → `[REDACTED]`).
- Add **1 partial-scope doc** (e.g. a department/role-scoped record) → `decision=partial` for out-of-scope roles (exercises the `[PARTIAL — scoped access]` token).
Both are synthetic, added to `corpus/` + `_demo_catalog()`. The 210-cell leak oracle + all governance suites must stay green; add cells/tests covering the new mask/partial docs.

## 7. Frontend — tabs (portfolio_app `/projects/clearance`)

Four top tabs, no login, pure client of the governed API via the existing Next route-handler proxy (`CLEARANCE_API_URL` server-side; no client-side governance; XSS-safe rendering; bundle no-secrets scan unchanged):
1. **Ask & Trace** (star) — §8.
2. **Datasets** — the full estate (§5), live-queryable vs catalog split, filters (live/catalog, real/synthetic, by class, by clearance), click-a-row → schema + sensitivity + reachable-by, plus the opaque-schema glossary. (Folds in the old "Corpus & Schema".)
3. **Leak Oracle** — the 210-cell grid (15 personas × 14 classes), green = no leak / red = leak, "✓ 210/210 · 0 leaks · CI gate green"; click a cell → opens that exact persona×class trace in Ask & Trace.
4. **Architecture** — the 5 ABC layers explained (Ingestion/Enrichment offline; Routing/Retrieval/Governance/Generation live), linking to run a live trace.

## 8. Frontend — Ask & Trace (the glass-box)

- **"What we have + what you can ask"** strip (from the catalog): the live docs as cards with class + clearance + 🔒; example-question chips; a note on reachability per clearance.
- **Ask bar** (free-text) + curated example chips; **clearance lens** chips: Intern / Analyst / Finance / CFO / **Auditor** (default = Auditor, full trace; persona lenses = "watch as" that persona).
- **On Run:** `POST /api/clearance/trace` → receive the full real `Trace` → **animated playback**:
  1. **Dissect** block fans the question into its parts (key terms, fingerprint, intent, detected topic).
  2. Each **stage** is a `takes → does → pushes out` card (blue / indigo / green); **the `pushes_out` of one is the `takes` of the next** (visible data flow); cards light up in sequence paced by the real `duration_ms`, streaming their logs.
  3. Each stage has a **"▾ detail"** revealing its real sub-steps + drill-down (candidate scores, the gate-by-gate decision, the loop grades, citation hashes).
  4. **Governance** is the centerpiece: an allow/mask/deny **bar**, blocked items **strike through** with "dropped before the model", masked → `[REDACTED]`, and a green **PROOF** line.
  5. **Output**: the governed answer + citations + "🔒 N withheld" (count only) + the "auditor saw them, persona never would" note.
- **"⚙ technical names" toggle** shows/hides the grey monospace labels (friendly-by-default for a non-technical auditor; precise for technical viewers).
- **Cold-start:** unchanged — the keep-alive cron + the proxy fast-fail already handle the free-tier wake; the trace proxy mirrors the query proxy's timeout/`waking` handling.

## 9. Data flow & sequence

`ask + clearance` → `POST /api/clearance/trace` (proxy, 8s timeout, cold-start → waking) → backend `POST /trace` (synthetic-only, rate-limited) → assemble real Trace (funnel + access.evaluate + tracer + candidates + loop + citations) → return → FE playback animates dissect → take→do→push-out chain → governed output.

## 10. Governance & safety invariants (must hold)

1. `/trace` runs **synthetic-profile only** — no real PII can appear.
2. `/query` stays **redacted** (`ClientRAGResponse`, no trail) — the auditor trace is the *only* un-redacted path, and it's the explicit demo endpoint.
3. An under-cleared persona's **generated answer** never contains denied content (the existing leak guarantee — the trace shows *why*, but the `result.answer` is the same governed output).
4. **Parity:** `trace.governance` decisions == `access.evaluate` (tested) — the UI cannot fake or drift.
5. FE has **no client-side governance**; the backend is the only gate; bundle has no secrets.
6. The 210-cell leak oracle + all phase governance suites stay green after the corpus enrichment.

## 11. Testing

- **Backend:** `/trace` returns a well-formed Trace; **parity test** (trace decisions == `access.evaluate` across a persona×class sample); `/query` redaction unchanged (regression); corpus-enrichment adds mask/partial cells and the **210-cell oracle stays 0-leak**; `/trace` refuses outside the synthetic profile; rate-limit applies; `make ci` 0-skip.
- **Frontend:** playback animates all stages; changing the lens re-runs and changes the trace; drill-downs render real data; the Datasets live/catalog split renders; Leak-Oracle cell → opens the right trace; bundle no-secrets scan clean; Playwright E2E drives Run → governed output + the lens contrast.
- **Deploy:** same Render backend (add endpoints + 2 corpus docs) + Vercel FE; keep-alive warm; extend `deploy-check.sh` to assert `/trace` returns a parity-correct, synthetic-only trace and a denied-persona's `result.answer` carries no restricted content.

## 12. Components & boundaries (for isolation)

- `trace.py` (backend) — pure assembler: pipeline internals → `Trace`. Testable in isolation against a fixed corpus; one job (assemble + redact-boundary), well-defined interface (`build_trace(question, session) -> Trace`).
- `/trace` + `/trace/catalog` endpoints — thin HTTP wrappers + guards.
- FE `TracePlayer` component — takes a `Trace`, animates it; no engine logic, pure presentation.
- FE `DatasetsTab`, `LeakOracleTab`, `ArchitectureTab` — independent, data from catalog/oracle endpoints.
- The corpus enrichment is data-only (no logic change to governance).

## 13. Follow-ons (tracked, not in this build)

- Wire real external connectors (catalog → live query-in-place) behind the existing ABCs.
- Optional true SSE streaming once off the free serverless tier.
- "Compare all clearances at once" mode in Ask & Trace (the side-by-side trace divergence).

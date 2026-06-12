# CLEARANCE Glass-Box UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans) per task. Steps use `- [ ]`. **Execution model:** the CLEARANCE fan-out — Shuri decomposes each phase into disjoint-file worker tasks + integrates on spine files (serial); Friday fans out parallel workers + **3 reviewers (security/governance · test-coverage · frontend)** at every phase gate; Friday runs independent verification + merges. TDD throughout; `make ci` 0-skip; the 210-cell leak oracle stays green at every gate.

**Goal:** Replace the persona-card demo with an auditor-framed glass-box that proves governance by animating the engine's REAL per-query trace, backed by a parity-tested `/trace` endpoint, with a full-estate Datasets tab.

**Architecture:** New backend `POST /trace` + `GET /trace/catalog` (synthetic-only) assemble the real trace from existing internals (funnel, `access.evaluate`, tracer, candidates, self-RAG grades, citations); the FE plays it back stage-by-stage. `/query` stays redacted. Spec: `docs/superpowers/specs/2026-06-12-clearance-glassbox-ui-design.md`.

**Tech Stack:** Python/FastAPI + pydantic (backend, `enterprise-rag-engine`), Next.js/React/TS (frontend, `portfolio_app /projects/clearance`), Render + Vercel deploy.

---

## The shared contract — `Trace` schema (spine; backend emits, FE consumes)

Both repos depend on this. Define it ONCE in `src/rag_engine/trace.py` (pydantic) and mirror it in `portfolio_app/src/app/projects/clearance/trace-types.ts`. Field names are normative.

```python
class SubStep(BaseModel):     label: str; io_label: str; ok: bool
class GateEval(BaseModel):    gate: str; result: str; fired: bool
class Candidate(BaseModel):   title: str; chunk_id: str; dense_score: float; final_rank: int
class GovDecision(BaseModel): title: str; decision: str  # allow|mask|partial|deny
                              gate_fired: str; reason: str; required_level: int | None; required_roles: list[str]
class Dissection(BaseModel):  raw: str; key_terms: list[str]; embedding_preview: list[float]  # first 8 dims
                              embedding_dim: int; intent_shape: str; detected_topic: str | None
class Stage(BaseModel):       id: str; layer: str; label: str
                              takes: str; does: str; pushes_out: str
                              duration_ms: int; status: str  # ok|warn
                              substeps: list[SubStep]
                              drilldown: dict  # stage-specific: {candidates:[Candidate]} | {gates:[{title,evals:[GateEval]}]} | {loop:[{step,grade}]} | {}
class Citation(BaseModel):    title: str; doc_hash: str; quote: str
class TraceResult(BaseModel): answer: str; citations: list[Citation]; admitted: int; n_withheld: int; access_denied: bool
class Trace(BaseModel):       query_dissection: Dissection; stages: list[Stage]
                              governance: list[GovDecision]; result: TraceResult
```

`POST /trace` body: `{question:str, roles:str, clearance:int}` (mirrors `/query`). `GET /trace/catalog` → `{sources:[{name,type,scale_badge,sensitivity_class,clearance_level,provenance_url,live_queryable}]}`.

---

## Phase sequence (each phase = workers on disjoint files → 3-reviewer gate → Friday verify+merge)

### Phase G0 — Corpus enrichment (data foundation; lands FIRST so mask/partial are live + oracle stays green)
**Why first:** the trace must show allow/mask/partial/deny live; today's 4-doc corpus only yields allow/deny. Nothing that asserts mask/partial can land before this.
**Files (disjoint):**
- Worker A — Create `corpus/customer_account_sample.md` (class **D** customer-PII record; masks at L2–3, raw at L4+) + its catalog entry in `_demo_catalog()` (`api.py`) / `demo_data.py`.
- Worker B — Create `corpus/dept_scoped_record.md` (a **partial-scope** doc → `partial` for out-of-scope roles) + catalog entry.
- Spine (Shuri) — wire both into `index_corpus`/`_CORPUS`; extend the access-matrix/oracle fixtures so the 210-cell oracle covers the new docs.
**Tests:** new docs trigger `decision=mask` (D@L2) and `decision=partial` live; `redact_chunk`→`[REDACTED]`/`[PARTIAL …]`; **210-cell oracle stays 0-leak**; `make ci` 0-skip.
**Gate:** governance reviewer (oracle parity + the new mask/partial cells bite under mutation), test-coverage reviewer. Friday: re-run oracle + a mask/partial probe.

### Phase G1 — Backend `/trace` assembler + endpoints + parity (depends on G0)
**Files (disjoint where possible; `trace.py` + `api.py` are spine/serial):**
- Spine (Shuri) — `src/rag_engine/trace.py`: `build_trace(question, session) -> Trace` — run the real pipeline instrumented, assemble Dissection + Stages (Routing/Memory/Retrieval/Governance/Generation/Response) with real `duration_ms` from the tracer, substeps, drilldowns (candidate scores, gate-by-gate `access.evaluate`, self-RAG grades, citation hashes), `governance[]`, and `result` (the persona's redacted view). REUSE the pipeline — do not fork governance logic.
- Spine (Shuri) — `api.py`: add `POST /trace` + `GET /trace/catalog` (synthetic-only guard via `assert_synthetic_only`/profile check; rate-limited; clearance clamp). Keep `/query` unchanged.
- Worker A — `GET /trace/catalog` data: assemble the 23-source list from `seeds/real/sources.py` + synthetic source metadata + the demo catalog; flag `live_queryable` (4 demo docs true, rest false). New `src/rag_engine/catalog/estate.py` (pure data assembler).
- Worker B — `tests/test_trace_parity.py`: for a persona×class sample, assert `trace.governance[i].decision == access.evaluate(chunk, session).decision` (the un-fakeable invariant).
- Worker C — `tests/test_trace_endpoint.py` + `tests/test_query_redaction_regression.py`: `/trace` shape + synthetic-only refusal + rate-limit; `/query` still returns redacted `ClientRAGResponse` (no trail).
- Worker D — extend `scripts/deploy-check.sh`: assert `/trace` returns a parity-correct synthetic trace and a denied-persona `result.answer` carries no restricted content.
**Tests:** parity test bites (mutate the assembler to diverge → fails); `/trace` synthetic-only; `/query` redaction regression green; `make ci` 0-skip.
**Gate:** security/governance reviewer (the trace can't leak more than `/query` allows for the persona result; parity holds; synthetic-only), test-coverage reviewer (parity + endpoint + regression bite). Friday: hit `/trace` live-style + mutation-probe parity.

### Phase G2 — FE scaffolding: 4 tabs + trace/catalog proxies + cold-start (depends on G1 endpoints)
**Files (disjoint):**
- Spine (Shuri) — `portfolio_app/src/app/projects/clearance/page.tsx`: 4-tab shell (Ask&Trace · Datasets · Leak Oracle · Architecture), tab state, no login.
- Worker A — `src/app/api/clearance/trace/route.ts` (proxy `/trace`, mirror the query proxy's 8s-timeout + cold-start `waking` handling, server-side `CLEARANCE_API_URL`).
- Worker B — `src/app/api/clearance/catalog/route.ts` (proxy `/trace/catalog`, same pattern).
- Worker C — `trace-types.ts` mirroring the `Trace` schema (the FE contract).
**Tests:** `next build` clean; bundle no-secrets scan clean; the tabs render; proxies handle cold-start.
**Gate:** frontend reviewer (XSS-safe, no client-side governance, server-side URL), security reviewer (bundle scan). Friday: build + scan + the existing Playwright smoke.

### Phase G3 — FE Ask & Trace: the TracePlayer (the centerpiece; depends on G1+G2)
**Files (disjoint):**
- Spine (Shuri) — `AskTraceTab.tsx`: data strip + ask bar + example chips + clearance lens; on Run → `POST /api/clearance/trace` → drive the player.
- Worker A — `TracePlayer.tsx`: animated playback — dissect block → per-stage `takes→does→pushes out` cards lighting up by real `duration_ms` → streaming logs.
- Worker B — `StageDrilldown.tsx`: the `▾ detail` expanders per stage (candidate-score table, gate-by-gate, self-RAG grades, citation hashes) + the `⚙ technical names` toggle.
- Worker C — `GovernanceBar.tsx` + the allow/mask/deny bar + strike-through-drop animation + the PROOF line + the output block (answer + `n_withheld` + the "auditor saw / persona never would" note).
**Tests:** playback animates all stages; lens change re-runs + changes the trace; drilldowns render real data; XSS-safe; pure client. `next build` + bundle scan clean.
**Gate:** frontend reviewer (interaction quality, accessibility, no client-side governance), test-coverage reviewer (the trace shape is honored; the answer == the redacted result, never the auditor governance detail leaking into the persona answer area). Friday: Playwright E2E — Run → governed output; switch lens Intern↔CFO → divergence.

### Phase G4 — FE Datasets · Leak Oracle · Architecture tabs (depends on G1 catalog + G2; parallel to G3)
**Files (disjoint):**
- Worker A — `DatasetsTab.tsx`: the 23-source estate from `/catalog`, live-queryable vs catalog split, filters (live/catalog, real/synthetic, by class, by clearance), row → inspect, + the opaque-schema glossary (`/glossary`).
- Worker B — `LeakOracleTab.tsx`: the 210-cell grid (green/red), "✓ 210/210 · 0 leaks", click a cell → set Ask&Trace to that persona×class + Run.
- Worker C — `ArchitectureTab.tsx`: the 5 ABC layers explained (offline vs live), link to run a trace.
**Tests:** each tab renders from its endpoint; cell-click wiring; bundle scan clean.
**Gate:** frontend reviewer, test-coverage reviewer. Friday: Playwright per tab.

### Phase G5 — Integration + deploy
- Wire all tabs; `make ci` 0-skip (backend); `next build` + bundle scan (FE); the full Playwright E2E (Run, lens contrast, drilldowns, tab nav, Datasets, Oracle cell→trace).
- Deploy: Render backend (the 2 corpus docs + `/trace` + `/trace/catalog` auto-deploy from main); `make deploy-check <url>` (incl. the new `/trace` assertions) = GATE B PASS; keep-alive already warm; merge FE preview → main → Vercel prod; smoke-test the live page (the 5 mockup behaviors).
**Gate:** all 3 reviewers on the integrated diff. Friday: live smoke-test (Playwright against prod) + deploy-check green.

---

## Self-review (coverage vs spec)
- §4 `/trace` → G1 (assembler+endpoint+parity). §5 catalog → G1 (estate) + G2/G4 (proxy+tab). §6 corpus enrichment → G0. §7 tabs → G2. §8 Ask&Trace → G3. §9 other tabs → G4. §10 invariants → tests in G0/G1 + reviewer gates. §11 testing → each phase's Tests + G5. §12 components → the file map above. §13 follow-ons → unchanged (catalog stays metadata; no SSE; no auth).
- Sequencing honored: G0 (corpus/mask) → G1 (trace/parity) before FE (G2→G3/G4) consumes it; oracle-green gate at G0 before mask/partial-dependent work.
- No placeholders: each phase has concrete files, the shared `Trace` contract is defined, tests are specific (parity bite, oracle-green, redaction regression, bundle scan).
- Type consistency: `Trace`/`Stage`/`GovDecision` field names are the single normative contract used by both repos.

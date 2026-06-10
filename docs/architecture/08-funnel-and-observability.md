# 8 — Funnel + observability

## The funnel (the PB-scale honesty)

The headline claim — "I can run RAG over petabytes" — is demonstrated by the **funnel**, not by
embedding a petabyte. `funnel/trace.py`:

- `FunnelStage` (frozen: `name` / `count` / `bytes` / `note` / `provenance_url`).
- `FunnelTrace.stage(...)` **enforces monotonic non-increasing** on the counted stages as they
  are added (raises `ValueError` on an increase — the whole point; `is_monotonic_non_increasing`
  + a falsification test pin it).
- `compute_funnel(catalog, candidate_counts, pb_tail_asset_ids)` heads the funnel with the
  catalog's **STATED PB-tail scale** (`scale_badge` / `provenance_url` per asset, count
  un-counted) then the real indexable stages in order:
  `indexable_derivative → structured_prefilter → coarse_ann → rerank → final_top_k`.

So the funnel shows: petabytes of stated source scale collapsing to the handful of chunks
(`final_top_k`) that actually reach the model. The demo `/funnel` endpoint renders this from a
synthetic `CatalogRegistry` (NYC-TLC ≈1.6B rows/~400 GB, GDELT ≈800M events, Meridian ≈40M rows)
— stated scale only, no row content (deep dive [§11](11-demo-and-deploy-security.md)).

## Tracing (TRANSPARENT)

`observability/tracer.py`:
- `Tracer.span(name, request_id, **attributes)` — a thin facade with a pluggable collector so the
  hot path never depends on a network export. `request_id` is propagated across spans
  (route → retrieve → govern → generate). `InMemorySpanCollector` is the no-creds default;
  OpenTelemetry spans are emitted if the SDK is present.
- `LangfuseExporter` (creds-gated) maps spans to Langfuse traces — **allowlist-filtered**: only
  metric keys (`LANGFUSE_ATTR_ALLOWLIST` — request_id/cost/tokens/mode/…) are exported, so a
  careless `span("generate", answer=…)` can never leak content. **OTel `set_attribute` is filtered
  too** (exporter-agnostic, P0.11b fix). `tests/test_langfuse_allowlist.py` mutation-proves both.

`pipeline.py` wraps retrieve/govern/generate in **metric-only spans** (no question/answer/chunk
text); `tests/test_pipeline_tracing.py` asserts a seeded PII sentinel never appears in any span.

## The audit sink (durable governance records)

`governance/audit_sink.py`:
- `AuditSink` (Protocol, `record_event(kind, detail)`); `InMemoryAuditSink` (no-creds);
  `SurrealAuditSink` (durable, queryable).
- Used for: malformed-row drops (`store/chunk_source.py` — RESILIENT, sink failure logged not
  raised), cache hits (deep dive [§9](09-semantic-cache.md), attributable, metric-only),
  CDC events (`cdc_applied` / `cdc_dropped`, deep dive [§10b](10b-cdc-and-reembedding.md)),
  extraction failures (deep dive [§10c](10c-multimodal.md)).

The audit records carry **no chunk content / PII** by construction (metric/identity fields only)
— mutation-proven (`tests/test_audit_sink.py::test_audit_record_contains_no_chunk_content`). The
operator-only governance trail (deep dive [§3](03-governance.md)) is audit-side; the HTTP client
never sees it.

**Wired-live vs gated:** in-memory tracer + audit are always on; Langfuse + SurrealDB audit are
gated. Wiring the Tracer through every pipeline stage with the Langfuse allowlist landed in
P0.11a W1.

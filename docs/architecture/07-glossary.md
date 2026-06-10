# 7 — The opaque-schema glossary (text_2 → "customer name")

The legacy `OldMart` warehouse (deep dive [§1](01-data-and-seeds.md)) has **meaningless column
names** — `tbl_44.text_2` is a customer full name, `tbl_71.text_2` is an order status. A
text-to-SQL agent can't write `SELECT customer_name` against it without a semantic layer. The
glossary IS that layer.

## The subsystem (`enrichment/schema_glossary/`)

| Module | Role |
|---|---|
| `glossary.py` | `GlossaryEntry` (`physical` / `table` / `means` / `synonyms` / `examples` / `confidence` / `source`) + `Glossary` (keyed by `(table, physical)`) |
| `view_miner.py` | `mine_views(views)` — reads legacy view DDL (`v_cust AS SELECT text_2 AS name FROM tbl_44`) as **documentation evidence**, returning `{(table, physical): meaning}` |
| `profiler.py` | profiles column **values** (regex/format — emails match `@`, IDs are UUID-like, loyalty tier is low-cardinality {1,2,3}) when there is no view evidence |
| `drafter.py` | LLM-drafted meanings (`fake` deterministic for tests / `groq`/`nvidia` gated) for columns neither mined nor profiled |
| `drift.py` | drift detection vs the mined set |
| `resolve.py` | `GlossaryResolver` — resolves a natural-language term to `(table, physical)` so the agent writes correct SQL |

## The per-table-aware resolution (the teaching point)

The glossary is **per-table**: "customer name" → `(tbl_44, text_2)`, but "order status" →
`(tbl_71, text_2)` — the **same physical name `text_2` means different things** in different
tables. `resolve.py` keeps that distinction; `tests/test_view_miner.py` +
`tests/test_glossary_to_sql_e2e.py` pin it (a question about customer name produces
`SELECT text_2 FROM tbl_44`, not `tbl_71`).

## The honest scope note (a tracked follow-on)

The view-miner mines **aliased view columns**, so the "drift-clean" claim is scoped to the
**mined set** (documented in `tests/test_glossary_drift.py::test_glossary_drift_clean_against_mined_columns`),
not the full physical estate. Broadening coverage (query logs / dbt manifests / profile-then-draft
every physical column) so drift-clean spans the full `legacy_mart` schema is a tracked P0.4
follow-on. The persisted glossary lives in SurrealDB (`tests/test_glossary_surreal_store.py`).

## In the demo

The `/glossary` metadata endpoint (deep dive [§11](11-demo-and-deploy-security.md)) exposes the
**mapping only** (table / physical / means / confidence) — `mine_views(LEGACY_VIEWS)` over the
synthetic warehouse — never example values or row data.

**Wired-live vs gated:** miner/profiler/resolver are local-tested; the LLM drafter is gated
(`fake` default). Wiring the resolver into the live text-to-SQL pipeline path is a tracked
follow-on.

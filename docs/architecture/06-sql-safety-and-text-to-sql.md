# 6 — SQL-safety (AST gate + cost guard) + text-to-SQL result masking

The warehouse path lets an LLM draft SQL over the PB tail — so it is wrapped in **two safety
gates** (the SQL can't be unsafe or unbounded) and the **result rows are masked by governance
before the model** (the P0.3b hard requirement).

## The AST read-only gate

`sql/ast_gate.py::assert_read_only(sql, dialect)` parses the SQL with **sqlglot** and refuses
anything that isn't a read-only SELECT — a `_FORBIDDEN` set covering `exp.Alter`, `exp.Merge`,
`exp.Command`, **`exp.Into`** (the `SELECT … INTO <table>` CTAS-bypass found by a P0.3a reviewer),
DML/DDL, and stacked statements. It additionally `tree.find(exp.Into)` as an explicit dual-guard.
`projection_sources(tree)` extracts the projection→source-column map so masking is driven by the
**validated AST source column**, not the LLM-chosen output key — defeating alias / case /
expression / `*` PII bypasses.

## The cost guard

`connectors/bigquery.py::GuardedBigQuery` is a 4-gate, fail-closed wrapper:
1. AST read-only validation (above);
2. a **dry-run** byte estimate;
3. dry-run bytes vs `maximum_bytes_billed` (`config.bq_max_bytes_billed`, default 1 GB) — over
   the cap is **REFUSED** before any spend;
4. the **same validated SQL** runs with `maximum_bytes_billed` set (dry-run == execute target —
   no estimate/execute divergence).

`config.bq_require_partition_filter` enforces partition pruning. The cost guard is **fully
unit-tested locally** (`tests/test_bq_cost_guard.py`) regardless of creds — the partition
soft-spot + INTO dual-guard are pinned.

## Text-to-SQL with governed result masking

`texttosql/agent.py::TextToSqlAgent.answer(question, mask)`:
1. draft SQL (`generation/openai_compat.py`: `FakeSqlGenerator` deterministic for tests;
   `OpenAICompatGenerator` for Groq/NVIDIA, gated);
2. **AST-validate first** + extract `projection_sources`;
3. run through `GuardedBigQuery`;
4. 🔴 **mask result rows by AST source BEFORE the model sees them**
   (`texttosql/result_masking.py::mask_rows`, driven by the projection map);
5. answer from the **masked** rows only.

`pipeline.py::RAGPipeline.query_warehouse(question, session, agent, asset)` (P0.11a W5 + the
11b fix) makes this **session-governance-driven**: it evaluates `access.evaluate` over the
warehouse asset's SecurityContext for the session — a `deny` **short-circuits to no rows**
(before drafting/running SQL); `mask`/`partial` proceed with column masking; the `ColumnPolicy`
is sourced from the catalog asset. `tests/test_pipeline_warehouse.py` mutation-proves: collapse
deny→mask → the raw non-flagged column surfaces → fails.

`tests/test_texttosql_agent_e2e.py` proves the masked column never enters the generator's input
context (a `RecordingGenerator` captures exactly what the "model" saw), and the alias/case PII
bypass vectors never reach it.

**Wired-live vs gated:** the AST gate + cost guard + result masking are fully local-tested;
live BigQuery + Groq/NVIDIA are creds-gated. The warehouse path is **not exposed as an HTTP
endpoint** in the demo (deep dive [§11](11-demo-and-deploy-security.md): minimal attack surface)
— it is pipeline-proven.

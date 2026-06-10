# Spike S4 — BigQuery cost-guard contract (proven locally, no creds)

**Date:** 2026-06-09 · **Owner:** Shuri · **Type:** throwaway probe (no product code) · **Status:** ✅ KEEP — the cost-guard contract is fully enforceable client-side, no creds required to prove it

> **Question:** Can the BigQuery cost guard (`maximum_bytes_billed` + mandatory partition filter + read-only AST gate + dry-run estimation) be enforced as a client-wrapper contract that REFUSES an unsafe query before it ever executes — and proven entirely LOCALLY with a mocked BigQuery client?

## 1. Method
- **`sqlglot==30.10.0`** for the read-only AST gate + BigQuery-dialect transpile. **No `google-cloud-bigquery` and no GCP creds needed** to prove the contract — the BigQuery client is a `FakeBQClient` that records `execute()` calls and returns a stubbed dry-run byte estimate.
- A `GuardedBigQuery.run(sql)` wrapper applies four gates in order; any failure raises `CostGuardError` and **`execute()` is never reached**.

## 2. The four-gate contract (all proven)

| Gate | Mechanism | Refuses |
|---|---|---|
| **1. Read-only AST** | `sqlglot.parse` → exactly ONE statement, top node must be `SELECT` (or `WITH`→SELECT); walk the tree, reject any `Insert/Update/Delete/Drop/Create/Alter/Merge/Command` node | DML, DDL, `Command`, multi-statement |
| **2. Mandatory partition filter** | the parsed `WHERE` must reference the table's `partition_col` | a query with no WHERE, or WHERE missing the partition column |
| **3. `maximum_bytes_billed`** | dry-run byte estimate vs the configured cap | estimate > cap (this is the `SELECT *` lever — projection cost shows up as bytes) |
| **4. Transpile** | `tree.sql(dialect="bigquery")` | — (normalizes to the BigQuery dialect before execute) |

## 3. Results (7/7 contracts hold)

```
[OK] pruned SELECT under cap                : PASSED (executed)
[OK] unpruned SELECT * (no partition filter): REFUSED (mandatory partition filter missing)
[OK] pruned but over byte cap               : REFUSED (estimate 5e9 > cap 1e9)
[OK] DELETE statement                       : REFUSED (non-SELECT: Delete)
[OK] stacked statement injection            : REFUSED (got 2 statements, want 1)
[OK] CREATE TABLE AS SELECT                  : REFUSED (non-SELECT: Create)
[OK] WITH cte (pruned)                       : PASSED (executed)
```
Layered-defense edge confirmed: `SELECT *` **with** a partition filter passes gates 1–2 but is caught by gate 3 (byte cap) when it would scan too much; under the cap it executes (the cap, not the AST, is the `SELECT *` lever — correct, since `SELECT *` is legal SQL, just expensive).

## 4. SECURE notes
- **Injection-safe:** the "exactly one statement" check kills stacked-statement injection (`...; DROP TABLE`); the AST walk kills any embedded DML/DDL.
- **Fail-closed:** every gate raises before `execute()`; the wrapper never runs an unvalidated string.
- Production adds **read-only credentials** (a second, independent guarantee) + a real `job_config.dry_run=True` to source the byte estimate from BigQuery instead of the stub.

## 5. Live path (creds-gated, NOT a blocker)
No `GOOGLE_APPLICATION_CREDENTIALS` / BigQuery sandbox creds in env at spike time → the **live confirmation is skipped** (noted, not a blocker). The *core* contract — refuse-before-execute — is fully proven against the mock; the live path only swaps `FakeBQClient.dry_run_bytes_for` for a real `dry_run` job and adds `maximum_bytes_billed` on the job config. P0.3a wires the live path as a `@pytest.mark.cloud`-style creds-gated test.

## 6. Verdict — ✅ KEEP
The cost guard is a deterministic, fully-local-testable client wrapper. **All unit tests for the SQL-safety + cost-guard contract run without creds** (the ground-rule requirement). P0.3a productionizes: real `google-cloud-bigquery` client behind the same wrapper, config-driven cap + partition column (CONFIGURABLE — no magic numbers), read-only creds, creds-gated live test.

## 7. Reproduce
Throwaway harness `/tmp/s4_spike.py` (venv `/tmp/s4venv`, `sqlglot` only). Not committed — this doc is the artifact.

*Spike complete. Feeds P0.3a: the `GuardedBigQuery` wrapper (4-gate contract), config-driven cap/partition, read-only creds, creds-gated live path.*

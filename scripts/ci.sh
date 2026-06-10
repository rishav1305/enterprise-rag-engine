#!/usr/bin/env bash
# Local CI gate — THE pre-merge gate for this repo (CI runs locally, not on
# GitHub Actions). Fails loudly on missing deps/binary or any UNEXPECTED skip of
# the headline governance/turbovec/SurrealDB tests (no false-green).
#
# Usage:  make ci    (or)    bash scripts/ci.sh
set -euo pipefail

# Interpreter: prefer $PYTHON, else python3, else python — so the gate runs on
# python3-only systems (this box has no `python` shim).
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
    if command -v python3 >/dev/null 2>&1; then PYTHON=python3
    elif command -v python >/dev/null 2>&1; then PYTHON=python
    else echo "FAIL: no python3/python interpreter found." >&2; exit 1; fi
fi

echo "== local CI gate =="
echo "python: $PYTHON ($("$PYTHON" --version 2>&1))"

# 1) enforce the dev env (turns importorskip/skipif guards into hard failures)
export RAG_DEV_ENV=1

# 2) surreal binary must be on PATH or at the documented fallback
if ! command -v surreal >/dev/null 2>&1; then
    if [ -x "$HOME/.surrealdb/surreal" ]; then
        export PATH="$HOME/.surrealdb:$PATH"
    else
        echo "FAIL: surreal binary not found (PATH or ~/.surrealdb/surreal)." >&2
        echo "      The SurrealDB parity/store tests would silently skip." >&2
        echo "      Install: curl -sSf https://install.surrealdb.com | sh" >&2
        exit 1
    fi
fi
echo "surreal: $(command -v surreal) ($(surreal version 2>/dev/null | head -1))"

# 3) assert the pinned dev deps are importable (don't let a missing dep skip)
"$PYTHON" - <<'PY'
import importlib.util, sys
missing = [m for m in ("turbovec", "surrealdb", "faker", "polars", "numpy", "pydantic", "sqlglot", "semantic_router", "opentelemetry")
           if importlib.util.find_spec(m) is None]
if missing:
    sys.exit(f"FAIL: dev deps missing: {missing}. Run `make dev`.")
import turbovec
assert getattr(turbovec, "__version__", "0.7.0")  # pinned ==0.7.0
print("dev deps OK (turbovec, surrealdb, faker, polars, numpy, pydantic, sqlglot, semantic_router, opentelemetry)")
PY

# 4) run the suite (cloud excluded — creds-gated, non-authoritative for the gate)
#    -W error on unexpected skips is enforced by the in-suite no-skip guards
#    (tests/test_ci_dependency_guard.py fails-not-skips in RAG_DEV_ENV=1).
echo "== pytest -m 'not cloud' =="
PYTHONPATH=src "$PYTHON" -m pytest -m "not cloud and not bq and not llm and not langfuse" -rs

# 5) belt-and-suspenders: assert ZERO skips among the headline test modules
echo "== no-skip assertion (headline governance/turbovec/SurrealDB tests) =="
SKIPS=$(PYTHONPATH=src "$PYTHON" -m pytest -m "not cloud and not bq and not llm and not langfuse" -rs -q \
    tests/test_turbovec_index.py tests/test_allowlist_prefilter.py \
    tests/test_turbovec_recall.py tests/test_oracle_parity.py \
    tests/test_surreal_store.py tests/test_surreal_connector.py \
    tests/test_turbovec_retriever_unit.py tests/test_c1_over_vector_e2e.py \
    tests/test_surreal_chunksource_unit.py tests/test_store_backed_e2e.py \
    tests/test_sql_safety_inline.py tests/test_sql_ast_gate.py tests/test_bq_cost_guard.py \
    tests/test_bigquery_connector.py tests/test_warehouse_governance.py \
    tests/test_texttosql_inline.py tests/test_result_masking.py \
    tests/test_semantic_router.py tests/test_texttosql_agent_e2e.py \
    tests/test_glossary_inline.py tests/test_glossary_profiler.py \
    tests/test_view_miner.py tests/test_glossary_drift.py \
    tests/test_glossary_to_sql_e2e.py tests/test_glossary_surreal_store.py \
    tests/test_catalog_scale_provenance.py tests/test_funnel.py \
    tests/test_observability.py tests/test_audit_sink.py \
    tests/test_audit_sink_surreal.py \
    tests/test_ci_dependency_guard.py 2>&1 | grep -c -E '^SKIPPED' || true)
if [ "$SKIPS" -ne 0 ]; then
    echo "FAIL: $SKIPS headline test(s) skipped — false-green risk." >&2
    exit 1
fi

echo "== lint =="
ruff check src tests

echo "PASS: local CI gate green (0 unexpected skips)."

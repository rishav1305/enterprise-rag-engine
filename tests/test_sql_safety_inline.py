"""P0.3a Batch-A inline tests (AST gate + cost guard). WORKER-A/B extend with the
exhaustive suites after the contract freeze."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402


def test_select_passes_dml_refused():
    from rag_engine.sql.ast_gate import AstGateError, assert_read_only
    assert_read_only("SELECT a FROM t WHERE d >= '2024-01-01'")  # ok
    for bad in ("DELETE FROM t", "DROP TABLE t", "INSERT INTO t VALUES (1)",
                "SELECT 1; DROP TABLE t", "CREATE TABLE x AS SELECT 1",
                "UPDATE t SET a=1", "MERGE INTO t USING s ON t.a=s.a "
                "WHEN MATCHED THEN UPDATE SET a=1"):
        with pytest.raises(AstGateError):
            assert_read_only(bad)


def test_cte_passes():
    from rag_engine.sql.ast_gate import assert_read_only
    assert_read_only("WITH x AS (SELECT a FROM t WHERE d>='2024-01-01') SELECT * FROM x")


def test_partition_filter_and_byte_cap():
    from rag_engine.sql.ast_gate import assert_read_only
    from rag_engine.sql.cost_guard import (CostGuardError, assert_partition_filter,
                                           assert_under_byte_cap)
    tree = assert_read_only("SELECT a FROM t WHERE pickup_datetime >= '2024-01-01'")
    assert_partition_filter(tree, "pickup_datetime")  # ok
    with pytest.raises(CostGuardError):
        assert_partition_filter(assert_read_only("SELECT a FROM t WHERE x=1"),
                                "pickup_datetime")  # missing partition col
    assert_under_byte_cap(500, 1000)  # ok
    with pytest.raises(CostGuardError):
        assert_under_byte_cap(5000, 1000)  # over cap


def test_config_cost_guard_defaults():
    from rag_engine.config import EngineConfig
    cfg = EngineConfig()
    assert cfg.bq_max_bytes_billed > 0
    assert cfg.bq_require_partition_filter is True
    assert cfg.bq_dialect == "bigquery"

"""P0.3a WORKER-B — exhaustive cost-guard cases (sql/cost_guard.py + config)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rag_engine.config import EngineConfig  # noqa: E402
from rag_engine.sql.ast_gate import assert_read_only  # noqa: E402
from rag_engine.sql.cost_guard import (  # noqa: E402
    CostGuardError, assert_partition_filter, assert_under_byte_cap,
)

_PART = "pickup_datetime"


def _tree(sql):
    return assert_read_only(sql)


def test_partition_filter_present_passes():
    assert_partition_filter(_tree(f"SELECT a FROM t WHERE {_PART} >= '2024-01-01'"), _PART)
    # partition col combined with other predicates still passes
    assert_partition_filter(
        _tree(f"SELECT a FROM t WHERE b=1 AND {_PART} BETWEEN '2024-01-01' AND '2024-02-01'"),
        _PART,
    )


def test_partition_filter_is_name_presence_only_documented_softspot():
    # PINS the documented contract: assert_partition_filter is NAME-PRESENCE only,
    # so it PASSES on a non-pruning predicate like `... OR pickup_datetime>'x'` and
    # on a same-named column from a join. This is intentional — the dry-run BYTE
    # CAP is the enforcing backstop (see cost_guard.py). If a future change tightens
    # this to a top-level conjunctive predicate, THIS test must be updated
    # deliberately (it documents that the soft-spot is a known, backstopped choice).
    assert_partition_filter(_tree(f"SELECT a FROM t WHERE vendor_id=1 OR {_PART}>'x'"), _PART)


def test_no_where_clause_refused():
    with pytest.raises(CostGuardError):
        assert_partition_filter(_tree("SELECT a FROM t"), _PART)


def test_where_without_partition_col_refused():
    with pytest.raises(CostGuardError):
        assert_partition_filter(_tree("SELECT a FROM t WHERE vendor_id = 1"), _PART)


def test_byte_cap_under_passes_over_refused():
    assert_under_byte_cap(0, 1000)
    assert_under_byte_cap(1000, 1000)          # exactly at cap is allowed
    with pytest.raises(CostGuardError):
        assert_under_byte_cap(1001, 1000)


def test_config_drives_cap_and_partition(monkeypatch):
    monkeypatch.setenv("BQ_MAX_BYTES_BILLED", "2048")
    monkeypatch.setenv("BQ_REQUIRE_PARTITION_FILTER", "0")
    cfg = EngineConfig()
    assert cfg.bq_max_bytes_billed == 2048
    assert cfg.bq_require_partition_filter is False
    # default (no env) is the 1 GB cap + partition required
    monkeypatch.delenv("BQ_MAX_BYTES_BILLED", raising=False)
    monkeypatch.delenv("BQ_REQUIRE_PARTITION_FILTER", raising=False)
    d = EngineConfig()
    assert d.bq_max_bytes_billed == 1_000_000_000
    assert d.bq_require_partition_filter is True


def test_select_star_with_partition_caught_only_by_byte_cap():
    # SELECT * passes the AST + partition gates (legal SQL); the byte cap is the
    # lever that refuses it when it would scan too much.
    tree = _tree(f"SELECT * FROM t WHERE {_PART} >= '2024-01-01'")
    assert_partition_filter(tree, _PART)        # passes partition gate
    assert_under_byte_cap(900, 1000)            # under cap -> ok
    with pytest.raises(CostGuardError):
        assert_under_byte_cap(9_999, 1000)      # over cap -> refused

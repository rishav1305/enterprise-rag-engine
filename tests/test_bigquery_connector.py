"""P0.3a — GuardedBigQuery integration (4-gate wrapper, fake client, no creds)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rag_engine.connectors.bigquery import FakeBigQueryClient, GuardedBigQuery  # noqa: E402
from rag_engine.sql.ast_gate import AstGateError  # noqa: E402
from rag_engine.sql.cost_guard import CostGuardError  # noqa: E402

_PART = "pickup_datetime"
_CAP = 1_000_000_000


def test_pruned_under_cap_executes():
    fake = FakeBigQueryClient(dry_run_bytes=500_000_000)
    g = GuardedBigQuery(fake, _PART, _CAP)
    rows = g.run(f"SELECT fare_amount FROM trips WHERE {_PART} >= '2024-01-01'")
    assert rows and fake.executed       # the safe query ran
    assert "fare_amount" in fake.executed[0]


def test_unpruned_refused_before_execute():
    fake = FakeBigQueryClient(dry_run_bytes=500_000_000)
    g = GuardedBigQuery(fake, _PART, _CAP)
    with pytest.raises(CostGuardError):
        g.run("SELECT * FROM trips")    # no partition filter
    assert not fake.executed            # REFUSED before execute (fail-closed)


def test_over_cap_refused_before_execute():
    fake = FakeBigQueryClient(dry_run_bytes=5_000_000_000)  # over the 1GB cap
    g = GuardedBigQuery(fake, _PART, _CAP)
    with pytest.raises(CostGuardError):
        g.run(f"SELECT a FROM trips WHERE {_PART} >= '2024-01-01'")
    assert not fake.executed


def test_dml_refused_before_execute():
    fake = FakeBigQueryClient(dry_run_bytes=1)
    g = GuardedBigQuery(fake, _PART, _CAP)
    with pytest.raises(AstGateError):
        g.run(f"DELETE FROM trips WHERE {_PART} < '2020-01-01'")
    assert not fake.executed


def test_injection_refused_before_execute():
    fake = FakeBigQueryClient(dry_run_bytes=1)
    g = GuardedBigQuery(fake, _PART, _CAP)
    with pytest.raises(AstGateError):
        g.run(f"SELECT a FROM trips WHERE {_PART}='x'; DROP TABLE trips")
    assert not fake.executed


def test_from_config_uses_config_cap_and_partition_flag(monkeypatch):
    monkeypatch.setenv("BQ_MAX_BYTES_BILLED", "1000")
    from rag_engine.config import EngineConfig
    fake = FakeBigQueryClient(dry_run_bytes=2000)  # over the 1000 cap from config
    g = GuardedBigQuery.from_config(fake, _PART, EngineConfig())
    assert g.max_bytes_billed == 1000
    with pytest.raises(CostGuardError):
        g.run(f"SELECT a FROM trips WHERE {_PART} >= '2024-01-01'")


def test_require_partition_filter_disabled_via_config(monkeypatch):
    # CONFIGURABLE: a non-partitioned table can disable the partition requirement
    monkeypatch.setenv("BQ_REQUIRE_PARTITION_FILTER", "0")
    from rag_engine.config import EngineConfig
    fake = FakeBigQueryClient(dry_run_bytes=10)
    g = GuardedBigQuery.from_config(fake, _PART, EngineConfig())
    g.run("SELECT a FROM small_dim_table WHERE name = 'x'")  # no partition col, allowed
    assert fake.executed

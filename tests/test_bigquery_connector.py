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
    # this is a CAP refusal, not an AST refusal: the dry-run DID run (estimate
    # computed), execute did not. Distinguishes it from a refuse-at-the-gate case.
    assert fake.dry_run_targets


def test_byte_cap_refuses_unpruned_via_dry_run_pruning_model():
    # partition GATE disabled -> the BYTE CAP is the lever that must catch an
    # unpruned scan (the fake models pruning: unpruned -> large bytes).
    fake = FakeBigQueryClient(dry_run_bytes=100_000_000, partition_col=_PART,
                              unpruned_bytes=9_000_000_000)
    g = GuardedBigQuery(fake, _PART, _CAP, require_partition_filter=False)
    # unpruned (no partition col in SQL) -> dry-run returns 9GB -> over the 1GB cap
    with pytest.raises(CostGuardError):
        g.run("SELECT a FROM trips WHERE vendor_id = 1")
    assert fake.dry_run_targets and not fake.executed   # cap refusal (dry-run ran)
    # pruned (partition col present) -> 100MB -> under cap -> executes
    rows = g.run(f"SELECT a FROM trips WHERE {_PART} >= '2024-01-01'")
    assert rows and fake.executed


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


def test_select_into_refused_execute_never_called():
    # CRITICAL regression: SELECT...INTO (CTAS-in-disguise) must be REFUSED before
    # execute, and must NOT be transpiled+shipped as a CREATE TABLE write.
    fake = FakeBigQueryClient(dry_run_bytes=1)
    g = GuardedBigQuery(fake, _PART, _CAP)
    with pytest.raises(AstGateError):
        g.run(f"SELECT a INTO exfil_table FROM trips WHERE {_PART} >= '2024-01-01'")
    assert not fake.executed
    assert not fake.dry_run_targets   # never even estimated (refused at the AST gate)


def test_dry_run_target_equals_execute_target():
    # IMPORTANT regression: the cap is checked against the SAME string that runs
    # (transpile FIRST, then dry-run AND execute the transpiled SQL).
    #
    # Uses a NON-CANONICAL input so transpile genuinely rewrites it: a double-
    # quoted literal `"2024-01-01"` becomes single-quoted `'2024-01-01'` in the
    # BigQuery dialect. So raw != transpiled, and this test BITES — mutating run()
    # back to dry_run_bytes_for(raw_sql) makes dry_run_target != execute_target.
    fake = FakeBigQueryClient(dry_run_bytes=10)
    g = GuardedBigQuery(fake, _PART, _CAP)
    raw = f'SELECT a FROM trips WHERE {_PART} >= "2024-01-01"'
    g.run(raw)
    assert fake.dry_run_targets and fake.executed
    assert fake.dry_run_targets[-1] == fake.executed[-1]    # same (transpiled) string
    assert fake.executed[-1] != raw                          # transpile DID rewrite it
    assert "'2024-01-01'" in fake.executed[-1]               # single-quoted in BQ dialect


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

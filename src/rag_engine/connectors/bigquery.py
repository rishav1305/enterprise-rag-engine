"""GuardedBigQuery — the safe query path to the BigQuery PB tail (P0.3a).

A thin wrapper that applies the S4 four-gate contract before any query reaches a
BigQuery client:

  1. read-only AST gate (single SELECT, no DML/DDL/injection),
  2. mandatory partition filter (config-gated),
  3. dry-run byte estimate vs ``maximum_bytes_billed``,
  4. transpile to the BigQuery dialect,

then execute. Any gate failure raises (``AstGateError``/``CostGuardError``) and
``execute`` is NEVER reached (fail-closed). The client is a ``BigQueryClient``
Protocol — a ``FakeBigQueryClient`` for local/no-creds tests, the real
``google-cloud-bigquery`` client for the creds-gated live path.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..config import EngineConfig
from ..sql.ast_gate import assert_read_only, transpile_bigquery
from ..sql.cost_guard import assert_partition_filter, assert_under_byte_cap


class BigQueryClient(Protocol):
    def dry_run_bytes_for(self, sql: str) -> int:
        """Bytes the query would scan (a BigQuery dry-run job estimate)."""
        ...

    def execute(self, sql: str, max_bytes_billed: int) -> list[Any]:
        """Run the (already-validated) SQL with maximum_bytes_billed set."""
        ...


class FakeBigQueryClient:
    """Local test double: records executes, returns a stubbed dry-run estimate."""

    def __init__(self, dry_run_bytes: int, rows: list[Any] | None = None) -> None:
        self.dry_run_bytes = dry_run_bytes
        self.rows = rows if rows is not None else [("row",)]
        self.executed: list[str] = []
        self.dry_run_targets: list[str] = []  # records what was estimated

    def dry_run_bytes_for(self, sql: str) -> int:
        self.dry_run_targets.append(sql)
        return self.dry_run_bytes

    def execute(self, sql: str, max_bytes_billed: int) -> list[Any]:
        self.executed.append(sql)
        return self.rows


class GuardedBigQuery:
    def __init__(
        self,
        client: BigQueryClient,
        partition_col: str,
        max_bytes_billed: int,
        require_partition_filter: bool = True,
        dialect: str = "bigquery",
    ) -> None:
        self.client = client
        self.partition_col = partition_col
        self.max_bytes_billed = max_bytes_billed
        self.require_partition_filter = require_partition_filter
        self.dialect = dialect

    @classmethod
    def from_config(cls, client: BigQueryClient, partition_col: str,
                    config: EngineConfig | None = None) -> "GuardedBigQuery":
        cfg = config or EngineConfig()
        return cls(
            client=client,
            partition_col=partition_col,
            max_bytes_billed=cfg.bq_max_bytes_billed,
            require_partition_filter=cfg.bq_require_partition_filter,
            dialect=cfg.bq_dialect,
        )

    def run(self, sql: str) -> list[Any]:
        # 1. read-only AST gate (raises AstGateError on any non-SELECT/injection)
        tree = assert_read_only(sql, dialect=self.dialect)
        # 2. mandatory partition filter (config-gated)
        if self.require_partition_filter:
            assert_partition_filter(tree, self.partition_col)
        # 3. transpile to the BigQuery dialect FIRST, then dry-run AND execute the
        #    SAME string. (Estimating the raw input but executing the transpiled
        #    string would check the cap against a query that isn't the one run.)
        bq_sql = transpile_bigquery(tree)
        estimate = self.client.dry_run_bytes_for(bq_sql)
        assert_under_byte_cap(estimate, self.max_bytes_billed)
        return self.client.execute(bq_sql, self.max_bytes_billed)

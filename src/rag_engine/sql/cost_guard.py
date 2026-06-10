"""BigQuery cost guard — mandatory partition filter + ``maximum_bytes_billed``.

The two cost levers, enforced before execution (spike S4):

  * **partition filter** — a query on a partitioned table MUST filter on the
    partition column, or it would scan the whole (PB-scale) table.
  * **byte cap** — a dry-run byte estimate must be under the configured
    ``maximum_bytes_billed``; this is the lever that catches expensive
    projections like ``SELECT *`` (legal SQL, but costly).

Both raise ``CostGuardError`` (fail-closed) — execution never proceeds.
"""

from __future__ import annotations

from sqlglot import exp


class CostGuardError(Exception):
    """Raised when a query would exceed the cost guard (partition / bytes)."""


def assert_partition_filter(tree: exp.Expression, partition_col: str) -> None:
    """Require the query's WHERE to reference ``partition_col``."""
    where = tree.find(exp.Where)
    if where is None:
        raise CostGuardError(
            f"no WHERE clause -> mandatory partition filter on {partition_col!r} missing"
        )
    cols = {c.name for c in where.find_all(exp.Column)}
    if partition_col not in cols:
        raise CostGuardError(
            f"mandatory partition filter on {partition_col!r} missing "
            f"(WHERE references {sorted(cols)})"
        )


def assert_under_byte_cap(estimated_bytes: int, max_bytes_billed: int) -> None:
    """Require the dry-run byte estimate to be at or under the cap."""
    if estimated_bytes > max_bytes_billed:
        raise CostGuardError(
            f"dry-run estimate {estimated_bytes} bytes > "
            f"maximum_bytes_billed {max_bytes_billed} bytes"
        )

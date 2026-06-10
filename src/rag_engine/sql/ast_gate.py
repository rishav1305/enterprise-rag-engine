"""Read-only SQL AST gate (sqlglot) — the SECURE gate for text-to-SQL.

Only a SINGLE ``SELECT`` (optionally wrapped in a ``WITH``) is allowed to reach
the warehouse. Anything else — DML, DDL, a bare ``Command``, or a stacked/multi
statement injection — is REFUSED here, before the query string ever touches a
BigQuery client. Proven by spike S4 (``docs/spikes/s4-bigquery-cost-guard.md``).
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

# Forbidden top-level / embedded statement nodes (DML + DDL + raw command).
_FORBIDDEN = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
    exp.Alter, exp.Merge, exp.Command,
)


class AstGateError(Exception):
    """Raised when a SQL string is not a single read-only SELECT."""


def assert_read_only(sql: str, dialect: str = "bigquery") -> exp.Expression:
    """Parse ``sql`` and assert it is exactly one read-only SELECT. Return the tree.

    Fail-closed: any parse failure, multi-statement, non-SELECT top node, or an
    embedded DML/DDL node raises ``AstGateError``.
    """
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except Exception as e:  # sqlglot.ParseError and friends
        raise AstGateError(f"unparseable SQL: {e}") from e

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise AstGateError(
            f"exactly one statement required, got {len(statements)} "
            f"(stacked-statement injection is refused)"
        )

    tree = statements[0]
    top = tree.this if isinstance(tree, exp.With) else tree
    if not isinstance(top, exp.Select):
        raise AstGateError(f"non-SELECT statement refused: {type(tree).__name__}")

    # belt-and-suspenders: reject any DML/DDL node anywhere in the tree
    for node in tree.walk():
        n = node[0] if isinstance(node, tuple) else node
        if isinstance(n, _FORBIDDEN):
            raise AstGateError(f"forbidden statement node: {type(n).__name__}")

    return tree


def transpile_bigquery(tree: exp.Expression) -> str:
    """Render the validated tree as BigQuery-dialect SQL."""
    return tree.sql(dialect="bigquery")

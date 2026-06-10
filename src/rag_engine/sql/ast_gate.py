"""Read-only SQL AST gate (sqlglot) — the SECURE gate for text-to-SQL.

Only a SINGLE ``SELECT`` (optionally wrapped in a ``WITH``) is allowed to reach
the warehouse. Anything else — DML, DDL, a bare ``Command``, or a stacked/multi
statement injection — is REFUSED here, before the query string ever touches a
BigQuery client. Proven by spike S4 (``docs/spikes/s4-bigquery-cost-guard.md``).
"""

from __future__ import annotations

# NB: `dataclass` is imported UNCONDITIONALLY at module top (added in c3a9085).
# A one-off NameError flake during P0.3b was root-caused to a transient where this
# import was added inside a function; it is now a top-level import, so the flake is
# confirmed-fixed (documented, not assumed) and cannot recur.
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

# Forbidden top-level / embedded statement nodes (DML + DDL + raw command).
# NB: `exp.Into` is in the set because `SELECT ... INTO <table>` parses as a
# top-level Select carrying an Into child — it would pass the SELECT check, then
# transpile to `CREATE TABLE x AS SELECT ...` (a DDL WRITE). It MUST be refused.
_FORBIDDEN = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
    exp.Alter, exp.Merge, exp.Command, exp.Into,
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

    # `SELECT ... INTO <table>` is a DDL WRITE in disguise (transpiles to CTAS):
    # refuse it explicitly with a clear message (the _FORBIDDEN walk below also
    # catches it; this named check is robust to AST-representation changes).
    if tree.find(exp.Into) is not None:
        raise AstGateError("SELECT ... INTO refused (it is a CREATE TABLE write)")

    # belt-and-suspenders: reject any DML/DDL node anywhere in the tree
    for node in tree.walk():
        n = node[0] if isinstance(node, tuple) else node
        if isinstance(n, _FORBIDDEN):
            raise AstGateError(f"forbidden statement node: {type(n).__name__}")

    return tree


def transpile_bigquery(tree: exp.Expression) -> str:
    """Render the validated tree as BigQuery-dialect SQL."""
    return tree.sql(dialect="bigquery")


@dataclass(frozen=True)
class ProjectionSource:
    """One SELECT output column resolved to its SOURCE base columns.

    ``output_key`` is the row key the result will carry (alias or column name).
    ``source_columns`` is the set of base columns the projection derives from
    (so an aliased / expression-wrapped masked column is still attributable).
    ``is_star`` marks ``SELECT *`` (the caller expands it to the asset's columns).
    ``resolvable`` is False when the projection's source can't be tied to a known
    base column (e.g. a literal or an opaque function) — callers FAIL CLOSED and
    redact such columns rather than assume they are safe.
    """

    output_key: str
    source_columns: frozenset[str]
    is_star: bool = False
    resolvable: bool = True


def projection_sources(tree: exp.Expression) -> list[ProjectionSource]:
    """Map each SELECT projection to its source base columns (for result masking).

    Resolves aliases (``customer_email AS em``), expressions over a column
    (``UPPER(customer_email)``), bare columns, and ``SELECT *``. This is what makes
    masking robust against an LLM choosing the output key: we mask off the SOURCE
    column from the validated AST, not the attacker-controlled alias.
    """
    select = tree.this if isinstance(tree, exp.With) else tree
    if not isinstance(select, exp.Select):
        return []
    out: list[ProjectionSource] = []
    for proj in select.expressions:
        if isinstance(proj, exp.Star):
            out.append(ProjectionSource("*", frozenset(), is_star=True))
            continue
        cols = frozenset(c.name for c in proj.find_all(exp.Column))
        key = proj.alias_or_name
        # A projection with no resolvable source column AND that isn't itself a
        # plain column reference (e.g. a literal/opaque fn) -> mark unresolvable so
        # the caller can fail closed.
        resolvable = bool(cols) or isinstance(proj, exp.Column)
        out.append(ProjectionSource(key, cols, resolvable=resolvable))
    return out

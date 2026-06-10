"""P0.3a WORKER-A — exhaustive read-only AST gate cases (sql/ast_gate.py)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rag_engine.sql.ast_gate import (  # noqa: E402
    AstGateError, assert_read_only, transpile_bigquery,
)

_ALLOWED = [
    "SELECT a FROM t WHERE d >= '2024-01-01'",
    "SELECT a, b, COUNT(*) FROM t WHERE d >= '2024-01-01' GROUP BY a, b",
    "SELECT a FROM t WHERE d >= '2024-01-01' ORDER BY a LIMIT 10",
    "WITH x AS (SELECT a FROM t WHERE d>='2024-01-01') SELECT * FROM x",
    "SELECT a FROM t WHERE d >= '2024-01-01' AND b IN (1,2,3)",
    "SELECT t.a, u.b FROM t JOIN u ON t.id=u.id WHERE t.d >= '2024-01-01'",
]

_REFUSED = [
    "DELETE FROM t WHERE d < '2020-01-01'",
    "DROP TABLE t",
    "INSERT INTO t (a) VALUES (1)",
    "UPDATE t SET a = 1 WHERE d = '2024-01-01'",
    "CREATE TABLE x AS SELECT a FROM t",
    "ALTER TABLE t ADD COLUMN c INT64",
    "MERGE INTO t USING s ON t.a=s.a WHEN MATCHED THEN UPDATE SET a=1",
    "SELECT a FROM t WHERE d='x'; DROP TABLE t",        # stacked injection
    "SELECT a FROM t; SELECT b FROM u",                  # multi-statement
    "TRUNCATE TABLE t",                                  # Command/DDL
    "GRANT SELECT ON t TO 'x'",                          # Command
    "not valid sql ;;;",                                 # unparseable
    # SELECT ... INTO is a DDL WRITE in disguise (transpiles to CREATE TABLE AS):
    "SELECT a INTO exfil_table FROM t WHERE d >= '2024-01-01'",
    "select * into exfil from t where d >= '2024-01-01'",   # lowercase
    "SELECT a, b INTO new_t FROM t",                         # no WHERE
    "WITH x AS (SELECT a FROM t) SELECT a INTO y FROM x",    # INTO inside a CTE chain
]


def test_select_into_does_not_transpile_to_ddl():
    # regression guard for the CRITICAL bypass: SELECT...INTO must be refused at
    # the gate, never reaching transpile (which would emit CREATE TABLE AS).
    with pytest.raises(AstGateError):
        assert_read_only("SELECT a INTO exfil FROM t WHERE d >= '2024-01-01'")


@pytest.mark.parametrize("sql", _ALLOWED)
def test_allowed_selects_pass(sql):
    tree = assert_read_only(sql)
    assert tree is not None


@pytest.mark.parametrize("sql", _REFUSED)
def test_refused_statements_raise(sql):
    with pytest.raises(AstGateError):
        assert_read_only(sql)


def test_transpile_to_bigquery_dialect():
    # a Postgres-ish quoted identifier transpiles to BigQuery dialect cleanly
    tree = assert_read_only('SELECT a FROM t WHERE d >= "2024-01-01"', dialect="bigquery")
    out = transpile_bigquery(tree)
    assert "SELECT" in out and "FROM t" in out


def test_empty_string_refused():
    with pytest.raises(AstGateError):
        assert_read_only("")


def test_subquery_with_dml_inside_refused():
    # a SELECT that smuggles a DML node anywhere must still be refused
    with pytest.raises(AstGateError):
        assert_read_only("SELECT a FROM t WHERE d='x'; INSERT INTO t VALUES (2)")

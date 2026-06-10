"""View/query-log miner — mine physical->meaning evidence from legacy SQL (P0.4).

A legacy view `SELECT text_2 AS name FROM tbl_44` IS documentation: the alias
`name` is what `tbl_44.text_2` means. Crucially this is PER-TABLE — `v_orders`
(`text_2 AS status FROM tbl_71`) gives `tbl_71.text_2` = "status". We use sqlglot
to parse each statement and attribute each `column AS alias` to its source table.
"""

from __future__ import annotations

from collections.abc import Mapping

import sqlglot
from sqlglot import exp


def _single_source_table(select: exp.Select) -> str | None:
    """Return the SINGLE source table, or None for 0 or multiple tables.

    Mining is scoped to single-table views: a JOIN/multi-table SELECT would let us
    misattribute a column to the wrong table (e.g. `SELECT t.text_2, u.text_2 ...`),
    so we REFUSE to mine it rather than guess. Distinct table NAMES (handles
    self-joins/aliases conservatively by name count).
    """
    tables = {t.name for t in select.find_all(exp.Table)}
    return next(iter(tables)) if len(tables) == 1 else None


def mine_views(views: Mapping[str, str], dialect: str = "bigquery") -> dict[tuple[str, str], str]:
    """Return {(table, physical) -> mined_meaning} from the view/query SQL.

    Only `physical_column AS alias` projections over a single source table yield
    evidence (the alias is the meaning, attributed to that table's physical column).
    """
    out: dict[tuple[str, str], str] = {}
    for sql in views.values():
        try:
            tree = sqlglot.parse_one(sql, read=dialect)
        except Exception:
            continue
        select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
        if select is None:
            continue
        table = _single_source_table(select)
        if table is None:
            continue
        for proj in select.expressions:
            # we want `Alias(this=Column, alias=...)` i.e. a renamed base column
            if isinstance(proj, exp.Alias) and isinstance(proj.this, exp.Column):
                physical = proj.this.name
                meaning = proj.alias
                if physical and meaning:
                    out[(table, physical)] = meaning
    return out

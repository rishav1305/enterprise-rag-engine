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


def _from_table(select: exp.Select) -> str | None:
    # the single source table of the SELECT (mining is scoped to single-table views)
    tbl = select.find(exp.Table)
    return tbl.name if tbl is not None else None


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
        table = _from_table(select)
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

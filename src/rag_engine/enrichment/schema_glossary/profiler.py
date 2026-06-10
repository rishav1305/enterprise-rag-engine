"""Value profiler — infer hints about a physical column from its values (P0.4).

No semantic name to go on (``text_2``), so we profile the VALUES: regex/format
class (email/uuid/numeric/name/enum), cardinality, null rate, distinct ratio.
These hints feed the LLM-drafter and corroborate the view-miner.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_NAME = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$")  # two-token capitalized


@dataclass(frozen=True)
class ColumnProfile:
    table: str
    physical: str
    n: int
    null_rate: float
    distinct_ratio: float      # distinct non-null / non-null count
    regex_class: str           # email | uuid | name | numeric | enum | text | empty


def _classify(values: list[Any]) -> str:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "empty"
    strs = [str(v) for v in non_null]
    if all(_EMAIL.match(s) for s in strs):
        return "email"
    if all(_UUID.match(s) for s in strs):
        return "uuid"
    if all(_NAME.match(s) for s in strs):
        return "name"
    if all(_is_number(v) for v in non_null):
        return "numeric"
    distinct = len(set(strs))
    if distinct <= max(1, len(strs) // 5) and distinct <= 12:
        return "enum"        # low-cardinality -> categorical
    return "text"


def _is_number(v: Any) -> bool:
    if isinstance(v, (int, float)):
        return True
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def profile_column(rows: Sequence[dict[str, Any]], table: str, physical: str) -> ColumnProfile:
    values = [r.get(physical) for r in rows]
    n = len(values)
    non_null = [v for v in values if v is not None]
    null_rate = (n - len(non_null)) / n if n else 0.0
    distinct_ratio = (len(set(str(v) for v in non_null)) / len(non_null)) if non_null else 0.0
    return ColumnProfile(
        table=table, physical=physical, n=n, null_rate=round(null_rate, 4),
        distinct_ratio=round(distinct_ratio, 4), regex_class=_classify(values),
    )


def profile_table(rows: Sequence[dict[str, Any]], table: str) -> dict[str, ColumnProfile]:
    """Profile every physical column seen in the rows."""
    cols: set[str] = set()
    for r in rows:
        cols.update(r.keys())
    return {c: profile_column(rows, table, c) for c in sorted(cols)}

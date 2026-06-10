"""Mask warehouse SQL result columns BEFORE the rows reach the model (P0.3b).

The 🔴 hard gate. Masking is driven by the **validated AST's projection→source
map**, NOT by the LLM-chosen output key — because the LLM controls aliasing:
``SELECT customer_email AS em`` or ``UPPER(customer_email)`` or ``SELECT *`` would
all dodge a name-match on the output key. We instead redact any output column
whose SOURCE (resolved from the AST) is — or derives from — a masked
``ColumnPolicy`` column.

Rules (fail-closed):
  * direct column / alias / expression over a masked column -> REDACT that output;
  * ``SELECT *`` -> redact the output keys matching masked asset columns;
  * a projection whose source can't be resolved to a known base column -> REDACT
    (don't assume it's safe);
  * identifier matching is casefolded (BigQuery identifiers are case-insensitive).

The masked-column set comes from the asset ``ColumnPolicy`` (single governance
source) — never a hardcoded list.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from ..catalog.asset import ColumnPolicy
from ..governance.masking import MaskReason, mask_value
from ..sql.ast_gate import ProjectionSource


# Sentinel: a projection whose source couldn't be resolved -> redact fail-closed.
class _FailClosed:
    pass


_FAILCLOSED = _FailClosed()


def _reason_token(col: ColumnPolicy) -> str:
    try:
        return mask_value(None, MaskReason(col.mask_reason.lower()))
    except ValueError:
        return mask_value(None, MaskReason.PII_MASK)  # fail-closed default


def mask_rows(
    rows: Iterable[dict[str, Any]],
    columns: Sequence[ColumnPolicy],
    mask: bool,
    projections: Sequence[ProjectionSource] | None = None,
) -> list[dict[str, Any]]:
    """Redact masked result columns by AST source (not output key). Copy-not-mutate.

    ``projections`` is the projection→source map from ``ast_gate.projection_sources``
    over the validated query. When omitted (legacy/no-AST callers) it falls back to
    a casefolded output-key match — but the AST path is the robust one and is what
    the agent uses.
    """
    rows = [dict(r) for r in rows]
    if not mask:
        return rows

    masked_by_name = {c.name.casefold(): c for c in columns if c.masked}
    if not masked_by_name:
        return rows

    # ---- AST-source-driven path (robust against aliases/case/expr/star) ----
    if projections is not None:
        redact: dict[str, object] = {}  # output_key.casefold() -> ColumnPolicy | _FAILCLOSED
        for p in projections:
            if p.is_star:
                continue  # masked asset columns appear under their own name -> handled below
            if not p.resolvable:
                redact[p.output_key.casefold()] = _FAILCLOSED  # can't resolve -> redact
                continue
            hit = next((masked_by_name[s.casefold()] for s in p.source_columns
                        if s.casefold() in masked_by_name), None)
            if hit is not None:
                redact[p.output_key.casefold()] = hit

        for row in rows:
            for key in list(row):
                kcf = key.casefold()
                col = redact.get(kcf)
                if col is None and kcf in masked_by_name:   # SELECT *-style direct hit
                    col = masked_by_name[kcf]
                if col is not None:
                    row[key] = (mask_value(None, MaskReason.PII_MASK)
                                if col is _FAILCLOSED else _reason_token(col))
        return rows

    # ---- fallback: casefolded output-key match (no AST available) ----
    for row in rows:
        for key in list(row):
            col = masked_by_name.get(key.casefold())
            if col is not None:
                row[key] = _reason_token(col)
    return rows

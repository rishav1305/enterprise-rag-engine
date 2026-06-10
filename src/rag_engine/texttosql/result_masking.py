"""Mask warehouse SQL result columns BEFORE the rows reach the model (P0.3b).

The 🔴 hard gate: a SELECT over a warehouse asset can return masked columns
(customer_email, NYC TLC coords, …). Those values must be redacted in the result
rows so they never enter the generator's context — exactly the C1 drop-before-
model invariant, applied at the columnar-result grain.

``mask`` is derived from the session's governance decision over the warehouse
asset: decision == "mask" -> mask=True (redact masked cols); "allow" (L4+) ->
mask=False (raw); "deny" -> the agent returns NO rows at all (handled upstream).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from ..catalog.asset import ColumnPolicy
from ..governance.masking import MaskReason, mask_value


def mask_rows(
    rows: Iterable[dict[str, Any]],
    columns: Sequence[ColumnPolicy],
    mask: bool,
) -> list[dict[str, Any]]:
    """Return rows with each masked column redacted (when ``mask``), else passthrough.

    Fail-closed: a column declared ``masked`` is redacted via its ``mask_reason``;
    an unrecognised reason falls back to PII redaction (never the raw value).
    """
    rows = [dict(r) for r in rows]  # copy — never mutate the caller's rows
    if not mask:
        return rows
    masked_cols = {c.name: c for c in columns if c.masked}
    if not masked_cols:
        return rows
    for row in rows:
        for name, col in masked_cols.items():
            if name in row:
                try:
                    reason = MaskReason(col.mask_reason.lower())
                except ValueError:
                    reason = MaskReason.PII_MASK  # fail-closed default
                row[name] = mask_value(row[name], reason)
    return rows

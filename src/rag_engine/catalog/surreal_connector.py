"""SurrealConnector — catalog discovery from SurrealDB rows.

Implements the SAME ``Connector`` surface as ``SeedConnector`` but sources assets
from a ``SurrealStore`` instead of the in-process estate. It reuses
``_CLASS_ROLES``/``_CLASS_LEVEL`` and the column-policy mapping from
``connector`` (single source — no governance drift), so a ``CatalogRegistry``
built from either connector yields identical asset SecurityContexts. That parity
is what lets the 210-cell oracle pass unchanged through the store swap.
"""

from __future__ import annotations

from collections.abc import Iterator

from ..schemas import SecurityContext
from .asset import CatalogAsset
from .connector import _CLASS_ROLES, Connector, column_policy_for


class SurrealConnector(Connector):
    def __init__(self, store) -> None:
        self.store = store

    def discover(self) -> Iterator[CatalogAsset]:
        for row in self.store.all_assets():
            asset_id = _record_id(row.get("id"))
            cls = row["cls"]
            yield CatalogAsset(
                asset_id=asset_id,
                vertical=row["vertical"],
                retrieval_mode=row["retrieval_mode"],
                security=SecurityContext(
                    allowed_roles=_CLASS_ROLES[cls],
                    clearance_level=row["level"],
                    owner_department=row.get("owner_department", "UNASSIGNED"),
                    sensitivity_class=cls,
                    need_to_know_roles=_CLASS_ROLES[cls],
                ),
                sensitivity_class=cls,
                columns=tuple(
                    column_policy_for(c["name"], c["pii"], c["masked"])
                    for c in row.get("columns", [])
                ),
                scale_badge=row.get("scale_badge", ""),
                provenance_url=row.get("provenance_url", ""),
                row_count=row.get("row_count", 0),
            )


def _record_id(rid) -> str:
    """Extract the bare record id from a SurrealDB RecordID (or str)."""
    # surrealdb RecordID has a `.record_id` attr; fall back to str split.
    rec = getattr(rid, "record_id", None)
    if rec is not None:
        return str(rec)
    s = str(rid)
    return s.split(":", 1)[1] if ":" in s else s

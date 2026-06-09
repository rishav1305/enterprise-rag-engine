"""Catalog asset model — asset- and column-level security footprint.

A ``CatalogAsset`` is the catalog's record of one Meridian data asset (one row in
the P0.1a manifest). It carries an asset-level ``SecurityContext`` plus per-column
policy, so governance can decide both *whether* an asset is admissible and *which
columns* must be masked for a given session.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import SecurityContext


class ColumnPolicy(BaseModel):
    """Per-column policy. ``mask_reason`` distinguishes PII redaction from a
    role-secured (field-ACL) field so the audit trail can explain *why*."""

    model_config = ConfigDict(frozen=True)

    name: str
    pii: bool = False
    masked: bool = False
    mask_reason: str = ""  # "PII_MASK" | "FIELD_ACL_MASK" | ""


class CatalogAsset(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset_id: str
    vertical: str
    retrieval_mode: str
    security: SecurityContext
    sensitivity_class: str
    columns: tuple[ColumnPolicy, ...] = Field(default_factory=tuple)
    # row-scoped partial-access predicate (e.g. Engineer sees own-component tickets)
    partial_scope: str = ""

    def masked_columns(self) -> set[str]:
        return {c.name for c in self.columns if c.masked}

    def column(self, name: str) -> ColumnPolicy | None:
        return next((c for c in self.columns if c.name == name), None)

"""Connector seam + the SeedConnector over the P0.1a Meridian estate.

A ``Connector`` discovers ``CatalogAsset``s from a source. The ``SeedConnector``
reads the deterministic P0.1a estate (``seeds.emit.build_estate``) and maps each
manifest asset to a ``CatalogAsset`` with an asset-level ``SecurityContext``
derived from its sensitivity class. Real backends (SurrealDB, BigQuery) land in
later phases behind this same ABC (CONFIGURABLE / multi-setup).
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from ..schemas import SecurityContext
from .asset import CatalogAsset, ColumnPolicy

# Make the repo-root `seeds` package importable (the catalog reads the governance
# source of truth directly — no hand-copied tables, no drift).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from seeds.access_matrix import CLASSES as _CLASSES  # noqa: E402

# class -> need-to-know roles, DERIVED from seeds.access_matrix (single source).
# I1 fix: no hand-copied EMPLOYEE injection. A class with no need_to_know_roles is
# level-only — its asset SecurityContext carries no role restriction, exactly as
# the access model intends (over-restricting non-EMPLOYEE roles was the drift bug).
_CLASS_ROLES: dict[str, list[str]] = {
    code: list(sc.need_to_know_roles) for code, sc in _CLASSES.items()
}
# per-class min clearance level, also derived (no magic numbers).
_CLASS_LEVEL: dict[str, int] = {code: sc.min_level for code, sc in _CLASSES.items()}


def column_policy_for(name: str, pii: bool, masked: bool) -> ColumnPolicy:
    """Single source for column-policy mapping (DRY across connectors).

    mask_reason distinguishes PII redaction from a role-secured (field-ACL) field.
    """
    return ColumnPolicy(
        name=name,
        pii=pii,
        masked=masked,
        mask_reason=("PII_MASK" if pii else ("FIELD_ACL_MASK" if masked else "")),
    )


class Connector(ABC):
    @abstractmethod
    def discover(self) -> Iterator[CatalogAsset]:
        """Yield the CatalogAssets this connector registers."""
        raise NotImplementedError


class SeedConnector(Connector):
    """Loads catalog assets from the P0.1a Meridian estate manifest."""

    def __init__(self, scale: float = 1.0) -> None:
        self.scale = scale

    def discover(self) -> Iterator[CatalogAsset]:
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]  # repo root holding seeds/
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from seeds.emit import build_estate  # noqa: E402

        manifest, _ = build_estate(scale=self.scale)
        for spec in manifest.assets:
            yield CatalogAsset(
                asset_id=spec.asset_id,
                vertical=spec.vertical,
                retrieval_mode=spec.retrieval_mode,
                security=SecurityContext(
                    allowed_roles=_CLASS_ROLES[spec.sensitivity_class],
                    clearance_level=spec.clearance_level,
                    owner_department=spec.owner_department,
                    sensitivity_class=spec.sensitivity_class,
                    need_to_know_roles=_CLASS_ROLES[spec.sensitivity_class],
                ),
                sensitivity_class=spec.sensitivity_class,
                columns=tuple(
                    column_policy_for(f.name, f.pii, f.masked) for f in spec.fields
                ),
                scale_badge=spec.scale_badge,
                provenance_url=spec.provenance_url,
                row_count=spec.row_count,
            )

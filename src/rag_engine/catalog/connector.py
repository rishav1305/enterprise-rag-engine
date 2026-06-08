"""Connector seam + the SeedConnector over the P0.1a Meridian estate.

A ``Connector`` discovers ``CatalogAsset``s from a source. The ``SeedConnector``
reads the deterministic P0.1a estate (``seeds.emit.build_estate``) and maps each
manifest asset to a ``CatalogAsset`` with an asset-level ``SecurityContext``
derived from its sensitivity class. Real backends (SurrealDB, BigQuery) land in
later phases behind this same ABC (CONFIGURABLE / multi-setup).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from ..schemas import SecurityContext
from .asset import CatalogAsset, ColumnPolicy

# class -> default allowed/need-to-know roles for the asset-level SecurityContext.
# Mirrors seeds/access_matrix.py CLASSES need_to_know (single source of governance truth).
_CLASS_ROLES: dict[str, list[str]] = {
    "A": [], "B": ["EMPLOYEE"], "C": ["EMPLOYEE"], "D": ["EMPLOYEE"],
    "E": ["FINANCE", "C_SUITE"], "F": ["C_SUITE"],
    "G": ["LEGAL", "C_SUITE", "STRATEGY"], "H": ["CISO", "SECURITY", "BOARD"],
    "I": ["FINANCE", "C_SUITE"], "J": ["EMPLOYEE"], "K": ["EMPLOYEE"],
    "L": ["EMPLOYEE"], "M": ["FINANCE", "C_SUITE"], "N": ["FINANCE", "C_SUITE"],
}


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
                    ColumnPolicy(
                        name=f.name,
                        pii=f.pii,
                        masked=f.masked,
                        mask_reason=(
                            "PII_MASK" if f.pii
                            else ("FIELD_ACL_MASK" if f.masked else "")
                        ),
                    )
                    for f in spec.fields
                ),
            )

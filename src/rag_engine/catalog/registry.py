"""In-memory catalog registry.

Holds the discovered ``CatalogAsset``s and answers the queries governance and the
router need (by id / vertical / sensitivity class). A SurrealDB-backed registry
lands in P0.2a behind this same surface (CONFIGURABLE / multi-setup).
"""

from __future__ import annotations

from .asset import CatalogAsset
from .connector import Connector


class CatalogRegistry:
    def __init__(self) -> None:
        self._assets: dict[str, CatalogAsset] = {}

    def load(self, connector: Connector) -> int:
        n = 0
        for asset in connector.discover():
            self._assets[asset.asset_id] = asset
            n += 1
        return n

    def get(self, asset_id: str) -> CatalogAsset:
        return self._assets[asset_id]

    def all(self) -> list[CatalogAsset]:
        return [self._assets[k] for k in sorted(self._assets)]

    def by_vertical(self, vertical: str) -> list[CatalogAsset]:
        return [a for a in self.all() if a.vertical == vertical]

    def by_class(self, sensitivity_class: str) -> list[CatalogAsset]:
        return [a for a in self.all() if a.sensitivity_class == sensitivity_class]

"""The data manifest — the single registry of every Meridian asset.

Each generator (synthetic) and fixture (real) registers an ``AssetSpec``. The
manifest feeds the catalog registry (P0.1b), the Sources UI page, and the funnel
scale badges. It is serialized deterministically to ``manifest.json``.

Every asset MUST declare a sensitivity class + masking policy (the masking-
completeness gate). PII fields are present-and-maskable, never absent.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .access_matrix import CLASSES


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    dtype: str
    pii: bool = False
    masked: bool = False  # masked for unauthorized roles (PII present-but-redacted)


@dataclass(frozen=True, slots=True)
class AssetSpec:
    asset_id: str
    in_story_name: str
    synthetic: bool
    source: str  # real source name or "synthetic"
    provenance_url: str  # clickable provenance (real) or "" (synthetic)
    scale_badge: str  # e.g. "≈1.6B rows · ~400 GB"
    connector: str
    vertical: str
    retrieval_mode: str  # vector | graph | structured | full-text | catalog | funnel
    sensitivity_class: str  # key into access_matrix.CLASSES
    clearance_level: int
    owner_department: str
    fields: tuple[FieldSpec, ...] = ()
    row_count: int = 0

    def __post_init__(self) -> None:
        if self.sensitivity_class not in CLASSES:
            raise ValueError(f"{self.asset_id}: unknown sensitivity class {self.sensitivity_class!r}")


class Manifest:
    """Ordered, deterministic registry of asset specs."""

    def __init__(self) -> None:
        self._assets: dict[str, AssetSpec] = {}

    def register(self, spec: AssetSpec) -> AssetSpec:
        if spec.asset_id in self._assets:
            raise ValueError(f"duplicate asset_id {spec.asset_id!r}")
        self._assets[spec.asset_id] = spec
        return spec

    @property
    def assets(self) -> list[AssetSpec]:
        # deterministic order by asset_id
        return [self._assets[k] for k in sorted(self._assets)]

    def validate_masking(self) -> list[str]:
        """Return a list of policy violations (empty = pass)."""
        errors: list[str] = []
        for a in self.assets:
            has_pii = any(f.pii for f in a.fields)
            if has_pii and not any(f.masked for f in a.fields):
                errors.append(f"{a.asset_id}: has PII fields but none are maskable")
        return errors

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "asset_count": len(self._assets),
            "synthetic_count": sum(1 for a in self.assets if a.synthetic),
            "real_count": sum(1 for a in self.assets if not a.synthetic),
            "assets": [asdict(a) for a in self.assets],
        }

    def to_json(self) -> str:
        # sort_keys + fixed separators => byte-stable serialization
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

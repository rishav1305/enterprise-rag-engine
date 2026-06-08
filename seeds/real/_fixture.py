"""Shared real-source fixture builder.

A real source contributes: an ``AssetSpec`` (catalog metadata), connection
config (no creds — those come from env at serve time, CONFIGURABLE pillar), a
provenance URL, a scale badge, and a ``sample_pull`` callable. The callable is
mocked in CI; live behaviour is wired in later phases (P0.3 BigQuery, etc.).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest


@dataclass(slots=True)
class RealSourceSpec:
    asset_id: str
    in_story_name: str
    source: str
    provenance_url: str
    scale_badge: str
    connector: str
    vertical: str
    retrieval_mode: str
    sensitivity_class: str
    clearance_level: int
    owner_department: str
    fields: tuple[FieldSpec, ...]
    connection: dict[str, Any]
    catalog_only: bool = False  # Common Crawl: no sample pull, ever


def build_fixture(manifest: Manifest, spec: RealSourceSpec,
                  sample_pull: Callable[..., list[dict]] | None = None) -> SourceOutput:
    asset = register(
        manifest,
        asset_id=spec.asset_id,
        in_story_name=spec.in_story_name,
        synthetic=False,
        source=spec.source,
        provenance_url=spec.provenance_url,
        scale_badge=spec.scale_badge,
        connector=spec.connector,
        vertical=spec.vertical,
        retrieval_mode=spec.retrieval_mode,
        sensitivity_class=spec.sensitivity_class,
        clearance_level=spec.clearance_level,
        owner_department=spec.owner_department,
        fields=spec.fields,
        row_count=0,  # real sources are queried in place; no rows materialized here
    )
    out = SourceOutput(asset=asset, rows=[])
    out.connection = dict(spec.connection)
    out.connection["catalog_only"] = spec.catalog_only
    out.connection["has_sample_pull"] = (sample_pull is not None) and not spec.catalog_only
    return out

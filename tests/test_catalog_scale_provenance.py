"""P0.5 Task 0 — scale + provenance surfaced on CatalogAsset (feeds the funnel)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from rag_engine.catalog.connector import SeedConnector  # noqa: E402
from rag_engine.catalog.registry import CatalogRegistry  # noqa: E402


def _registry():
    reg = CatalogRegistry()
    reg.load(SeedConnector(scale=0.01))
    return reg


def test_real_asset_carries_scale_and_provenance():
    tlc = _registry().get("nyc_tlc_trips")
    assert tlc.scale_badge        # "≈1.6B rows · ~400 GB"
    assert tlc.provenance_url.startswith("http")


def test_synthetic_asset_carries_row_count():
    hr = _registry().get("hr_records")
    assert hr.row_count > 0        # materialized synthetic rows
    assert hr.scale_badge          # has a scale badge too


def test_common_crawl_pb_tail_scale_stated():
    cc = _registry().get("common_crawl")
    assert "PB" in cc.scale_badge  # the stated PB-tail scale for the funnel
    assert cc.provenance_url.startswith("http")

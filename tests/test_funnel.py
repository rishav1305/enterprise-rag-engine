"""P0.5 WORKER-A — funnel trace + monotonic-reduction + catalog PB-tail scale."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

from rag_engine.catalog.connector import SeedConnector  # noqa: E402
from rag_engine.catalog.registry import CatalogRegistry  # noqa: E402
from rag_engine.funnel.trace import FunnelTrace, compute_funnel  # noqa: E402


def test_funnel_is_monotonic_non_increasing():
    t = FunnelTrace()
    t.stage("raw_tail", count=None, bytes=10**15, note="PB (stated, BigQuery)")
    t.stage("indexable_derivative", count=50_000, bytes=19_000_000)
    t.stage("structured_prefilter", count=4_000)
    t.stage("coarse_ann", count=200)
    t.stage("rerank", count=8)
    t.stage("final_top_k", count=5)
    assert t.is_monotonic_non_increasing()
    assert t.counted == [50_000, 4_000, 200, 8, 5]
    assert t.reduction_factor() == 10_000.0       # 50000 -> 5


def test_funnel_rejects_an_increase():
    t = FunnelTrace()
    t.stage("coarse", count=200)
    with pytest.raises(ValueError):
        t.stage("rerank", count=500)              # the funnel must only reduce


def test_compute_funnel_from_catalog_pb_tail():
    reg = CatalogRegistry()
    reg.load(SeedConnector(scale=0.01))
    counts = {"indexable_derivative": 50_000, "structured_prefilter": 4_000,
              "coarse_ann": 200, "rerank": 8, "final_top_k": 5}
    t = compute_funnel(reg, counts, pb_tail_asset_ids=("nyc_tlc_trips", "common_crawl"))
    rows = t.to_rows()
    # the PB tail heads the funnel with stated scale + provenance
    pb = [r for r in rows if r["stage"].startswith("pb_tail")]
    assert any("≈1.6B" in r["note"] or "rows" in r["note"] for r in pb)
    assert all(r["provenance_url"].startswith("http") for r in pb)
    # the counted indexable path is monotonic
    assert t.is_monotonic_non_increasing()
    assert t.counted[-1] == 5


def test_none_count_pb_tail_does_not_break_monotonic():
    t = FunnelTrace()
    t.stage("pb_a", count=None, note="PB")
    t.stage("pb_b", count=None, note="PB")
    t.stage("indexable", count=1000)
    t.stage("final", count=5)
    assert t.is_monotonic_non_increasing()
    assert t.counted == [1000, 5]


def test_reduction_factor_single_stage():
    t = FunnelTrace()
    t.stage("only", count=42)
    assert t.reduction_factor() == 42.0

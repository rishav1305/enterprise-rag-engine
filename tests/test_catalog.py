"""P0.1b — catalog layer tests (asset, connector, registry, pipeline wiring)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.catalog.asset import CatalogAsset, ColumnPolicy  # noqa: E402
from rag_engine.schemas import SecurityContext  # noqa: E402


def test_catalog_asset_carries_security_and_columns():
    a = CatalogAsset(
        asset_id="hr_records",
        vertical="PEOPLE",
        retrieval_mode="vector",
        security=SecurityContext(allowed_roles=["FINANCE", "C_SUITE"], clearance_level=5),
        sensitivity_class="F",
        columns=(
            ColumnPolicy(name="salary", pii=True, masked=True, mask_reason="PII_MASK"),
            ColumnPolicy(name="dept", pii=False, masked=False),
        ),
    )
    assert a.sensitivity_class == "F"
    assert a.masked_columns() == {"salary"}
    assert a.column("salary").mask_reason == "PII_MASK"


def test_seed_connector_yields_catalog_assets():
    from rag_engine.catalog.connector import SeedConnector
    conn = SeedConnector(scale=0.01)
    assets = list(conn.discover())
    ids = {a.asset_id for a in assets}
    # P0.1a estate: 18 synthetic + 7 real = 25 catalog assets
    assert len(assets) == 25
    assert "hr_records" in ids and "legacy_mart_tbl_71" in ids and "nyc_tlc_trips" in ids
    hr = next(a for a in assets if a.asset_id == "hr_records")
    assert hr.sensitivity_class == "F"
    assert "salary" in hr.masked_columns()


def test_registry_loads_and_queries_by_vertical_and_class():
    from rag_engine.catalog.connector import SeedConnector
    from rag_engine.catalog.registry import CatalogRegistry
    reg = CatalogRegistry()
    n = reg.load(SeedConnector(scale=0.01))
    assert n == 25
    assert reg.get("hr_records").sensitivity_class == "F"
    finance = reg.by_vertical("FINANCE")
    assert {a.asset_id for a in finance} >= {"prerelease_financials", "payments_ledger"}
    e_class = reg.by_class("E")
    assert all(a.sensitivity_class == "E" for a in e_class)
    assert {a.asset_id for a in e_class} == {"prerelease_financials"}


def test_pipeline_accepts_catalog_registry():
    from rag_engine import RAGPipeline
    from rag_engine.catalog.connector import SeedConnector
    from rag_engine.catalog.registry import CatalogRegistry
    reg = CatalogRegistry()
    reg.load(SeedConnector(scale=0.01))
    p = RAGPipeline(catalog=reg)
    assert p.catalog is reg
    assert p.catalog.get("hr_records").sensitivity_class == "F"


def test_pipeline_catalog_is_optional():
    # backward compat: pipeline still constructs with no catalog
    from rag_engine import RAGPipeline
    p = RAGPipeline()
    assert p.catalog is None

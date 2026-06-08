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

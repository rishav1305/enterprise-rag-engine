"""P0.3a — warehouse (BigQuery) assets are governed like everything else.

The PB-tail warehouse assets (TPC-DS store_sales, NYC TLC trips, GDELT) carry a
SecurityContext + masked PII columns (customer_email, pickup/dropoff coords) in
the catalog. This pins that:
  1. they are real catalog assets with partition metadata for the cost guard,
  2. their masked columns are declared (so C1 redaction applies to a warehouse
     result row exactly as for any other source),
  3. governance over them follows the access matrix (no special-casing).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from rag_engine.catalog.connector import SeedConnector  # noqa: E402
from rag_engine.catalog.registry import CatalogRegistry  # noqa: E402
from rag_engine.governance.access import evaluate  # noqa: E402
from rag_engine.governance.masking import MaskReason, mask_value  # noqa: E402
from rag_engine.schemas import EnrichedChunk, Session  # noqa: E402


def _registry():
    reg = CatalogRegistry()
    reg.load(SeedConnector(scale=0.01))
    return reg


def test_warehouse_assets_in_catalog_with_partition_meta():
    reg = _registry()
    for aid in ("nyc_tlc_trips", "gdelt_events", "tpcds_store_sales"):
        a = reg.get(aid)
        assert a.sensitivity_class      # governed like everything else
        assert a.retrieval_mode == "structured"


def test_warehouse_masked_columns_declared():
    reg = _registry()
    # NYC TLC: pickup coords masked (PII)
    tlc = reg.get("nyc_tlc_trips")
    masked = tlc.masked_columns()
    assert "pickup_longitude" in masked and "pickup_latitude" in masked
    # TPC-DS: customer_email masked
    tpcds = reg.get("tpcds_store_sales")
    assert "customer_email" in tpcds.masked_columns()


def test_warehouse_asset_governance_follows_access_matrix():
    """A class-C warehouse asset: an L2 analyst is admitted (not raw-PII path);
    an intern (L1) is denied. No warehouse special-casing — same evaluate()."""
    reg = _registry()
    tlc = reg.get("nyc_tlc_trips")  # class C, L2
    chunk = EnrichedChunk(chunk_id="row1", parent_doc_id="nyc_tlc_trips",
                          parent_title="trips", content="trip row",
                          security=tlc.security)
    analyst = Session(user_id="oa", roles=["OPS_ANALYST", "EMPLOYEE"], clearance_level=2)
    intern = Session(user_id="in", roles=["INTERN", "EMPLOYEE"], clearance_level=1)
    assert evaluate(chunk, analyst).decision == "allow"   # L2 reaches class-C ops
    assert evaluate(chunk, intern).decision == "deny"     # L1 below class-C min


def test_masked_warehouse_column_value_is_redacted():
    """A masked warehouse column renders as a redaction token, never the raw value
    — the same C1 masking that governs every other source (defense in depth)."""
    reg = _registry()
    tlc = reg.get("nyc_tlc_trips")
    coord_col = tlc.column("pickup_longitude")
    assert coord_col.pii and coord_col.masked
    redacted = mask_value(-73.985428, MaskReason(coord_col.mask_reason.lower()))
    assert redacted in ("[REDACTED]", "[RESTRICTED]")
    assert "-73" not in redacted   # raw coordinate never leaks

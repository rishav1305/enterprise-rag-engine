"""The opaque-schema legacy warehouse (OldMart, acq. 2019) — the glossary showcase.

Column/table names carry NO semantic signal (tbl_44, text_2). Emits the §8 seed:
the physical tables, the physical->meaning map, and a legacy VIEW
(``v_cust AS SELECT text_2 AS name FROM tbl_44``) that the glossary miner (P0.4)
uses as evidence. World bible §8.
"""

from __future__ import annotations

from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

# §8 physical -> meaning map (the glossary's ground truth target)
GLOSSARY_TRUTH: dict[str, str] = {
    "tbl_44": "customers",
    "tbl_44.text_1": "customer_id",
    "tbl_44.text_2": "full_name",
    "tbl_44.text_5": "email",
    "tbl_44.num_3": "loyalty_tier",
    "tbl_71": "orders",
    "tbl_71.num_7": "order_total",
    "tbl_71.text_2": "order_status",
}

# legacy view definitions the miner reads as documentation evidence
LEGACY_VIEWS: dict[str, str] = {
    "v_cust": "SELECT text_1 AS customer_id, text_2 AS name, text_5 AS email FROM tbl_44",
    "v_orders": "SELECT text_1 AS order_id, num_7 AS total, text_2 AS status FROM tbl_71",
}

_STATUS = ["placed", "shipped", "returned"]


def generate(manifest: Manifest, scale: float = 1.0, n_customers: int = 5_000,
             n_orders: int = 12_000) -> SourceOutput:
    rng = derive_rng("legacy_mart")
    ncu = max(1, int(n_customers * scale))
    nor = max(1, int(n_orders * scale))

    # tbl_44 (customers) — text_2 = full_name (PII, masked), text_5 = email (PII, masked)
    cust_rows = []
    cust_ids = []
    for i in range(ncu):
        cid = rng.faker.uuid4()
        cust_ids.append(cid)
        cust_rows.append({
            "table": "tbl_44",
            "text_1": cid,                        # customer_id
            "text_2": rng.faker.name(),           # full name (PII)
            "text_5": rng.faker.email(),          # email (PII)
            "num_3": int(rng.np.integers(1, 4)),  # loyalty tier {1,2,3}
        })
    # tbl_71 (orders) — text_2 = order_status (NOT PII); num_7 = order_total
    order_rows = []
    for i in range(nor):
        order_rows.append({
            "table": "tbl_71",
            "text_1": f"ORD-{i:06d}",
            "fk_text_1": cust_ids[int(rng.np.integers(0, ncu))],  # -> tbl_44
            "num_7": round(float(rng.np.uniform(5.0, 2_000.0)), 2),  # order total
            "text_2": _STATUS[int(rng.np.integers(0, len(_STATUS)))],  # order status
        })

    # I1: per-table masking. tbl_44.text_2 (name) masked; tbl_71.text_2 (status) NOT.
    cust_asset = register(
        manifest,
        asset_id="legacy_mart_tbl_44",
        in_story_name="OldMart legacy warehouse — customers (tbl_44, opaque schema)",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈5k customers (opaque schema)",
        connector="Warehouse (legacy_mart)",
        vertical="COMMERCE",
        retrieval_mode="structured",
        sensitivity_class="D",  # customer PII -> masking
        clearance_level=3,
        owner_department="COMMERCE",
        fields=(
            FieldSpec("text_1", "str"),
            FieldSpec("text_2", "str", pii=True, masked=True),  # full_name -> masked
            FieldSpec("text_5", "str", pii=True, masked=True),  # email -> masked
            FieldSpec("num_3", "int"),
        ),
        row_count=len(cust_rows),
    )
    order_asset = register(
        manifest,
        asset_id="legacy_mart_tbl_71",
        in_story_name="OldMart legacy warehouse — orders (tbl_71, opaque schema)",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈12k orders (opaque schema)",
        connector="Warehouse (legacy_mart)",
        vertical="COMMERCE",
        retrieval_mode="structured",
        sensitivity_class="C",  # orders are team-ops; no PII columns
        clearance_level=2,
        owner_department="COMMERCE",
        fields=(
            FieldSpec("text_1", "str"),
            FieldSpec("fk_text_1", "str"),
            FieldSpec("num_7", "float"),       # order total
            FieldSpec("text_2", "str"),        # order_status -> NOT PII, NOT masked
        ),
        row_count=len(order_rows),
    )

    # Primary output is tbl_44; carry tbl_71 + glossary metadata on connection so the
    # emitter writes both row files and the glossary truth.
    out = SourceOutput(asset=cust_asset, rows=cust_rows)
    out.connection = {
        "glossary_truth": GLOSSARY_TRUTH,
        "legacy_views": LEGACY_VIEWS,
        "secondary_asset_id": order_asset.asset_id,
        "secondary_rows": order_rows,
    }
    return out

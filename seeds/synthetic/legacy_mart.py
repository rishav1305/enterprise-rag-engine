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

    rows = []
    # tbl_44 (customers) — physical column names only
    cust_ids = []
    for i in range(ncu):
        cid = rng.faker.uuid4()
        cust_ids.append(cid)
        rows.append({
            "table": "tbl_44",
            "text_1": cid,                       # customer_id
            "text_2": rng.faker.name(),          # full name
            "text_5": rng.faker.email(),         # email
            "num_3": int(rng.np.integers(1, 4)),  # loyalty tier {1,2,3}
        })
    # tbl_71 (orders) — FK text_1 -> tbl_44.text_1
    for i in range(nor):
        rows.append({
            "table": "tbl_71",
            "text_1": f"ORD-{i:06d}",
            "fk_text_1": cust_ids[int(rng.np.integers(0, ncu))],  # -> tbl_44
            "num_7": round(float(rng.np.uniform(5.0, 2_000.0)), 2),  # order total
            "text_2": _STATUS[int(rng.np.integers(0, len(_STATUS)))],  # order status
        })

    asset = register(
        manifest,
        asset_id="legacy_mart",
        in_story_name="OldMart legacy warehouse (opaque schema)",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈5k customers · 12k orders (opaque schema)",
        connector="Warehouse (legacy_mart)",
        vertical="COMMERCE",
        retrieval_mode="structured",
        sensitivity_class="D",  # contains customer PII (name/email) -> masking
        clearance_level=3,
        owner_department="COMMERCE",
        fields=(
            FieldSpec("text_1", "str"),
            FieldSpec("text_2", "str", pii=True, masked=True),  # name OR status (table-dependent)
            FieldSpec("text_5", "str", pii=True, masked=True),  # email
            FieldSpec("num_3", "int"),
            FieldSpec("num_7", "float"),
        ),
        row_count=len(rows),
    )
    out = SourceOutput(asset=asset, rows=rows)
    out.connection = {"glossary_truth": GLOSSARY_TRUTH, "legacy_views": LEGACY_VIEWS}
    return out

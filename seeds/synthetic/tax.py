"""Corporate tax filings/provisions (re-included domain — class M, L5 pre-filing).

COHERENCE: tax provision derives from coherence segment revenue totals.
"""

from __future__ import annotations

from .._coherence import anchors
from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_JURISDICTIONS = ["US-FED", "US-NY", "UK", "SG", "BR"]


def generate(manifest: Manifest, scale: float = 1.0) -> SourceOutput:
    rng = derive_rng("tax")
    rev = anchors().segment_revenue
    rows = []
    for quarter, seg_rev in rev.items():
        total_rev = sum(seg_rev.values())
        for jur in _JURISDICTIONS:
            rate = float(rng.np.uniform(0.10, 0.28))
            rows.append({
                "filing_id": f"TAX-{quarter}-{jur}",
                "quarter": quarter,
                "jurisdiction": jur,
                "taxable_base": round(total_rev * float(rng.np.uniform(0.1, 0.4)), 2),
                "provision": round(total_rev * rate * 0.25, 2),
                "status": "pre-filing",
            })
    asset = register(
        manifest,
        asset_id="tax_filings",
        in_story_name="Corporate tax filings/provisions",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈8 quarters × jurisdictions",
        connector="Tax / warehouse",
        vertical="FINANCE",
        retrieval_mode="structured",
        sensitivity_class="M",
        clearance_level=5,
        owner_department="FINANCE",
        fields=(
            FieldSpec("filing_id", "str"),
            FieldSpec("quarter", "str"),
            FieldSpec("jurisdiction", "str"),
            FieldSpec("taxable_base", "float"),
            FieldSpec("provision", "float"),
            FieldSpec("status", "str"),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

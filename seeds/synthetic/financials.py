"""Pre-release financials — class E (L5), rolls up from coherence segment revenue.

COHERENCE: projections derive from ``anchors().segment_revenue`` so the numbers
tie to the TPC-DS-shaped sales aggregates. World bible §7 + §10.
"""

from __future__ import annotations

from .._coherence import anchors
from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest


def generate(manifest: Manifest, scale: float = 1.0) -> SourceOutput:
    rng = derive_rng("financials")
    rev = anchors().segment_revenue
    rows = []
    for quarter, seg_rev in rev.items():
        for segment, revenue in seg_rev.items():
            # projection = actual revenue * a deterministic optimism factor (draft)
            factor = 1.0 + float(rng.np.uniform(0.03, 0.12))
            rows.append({
                "segment": segment,
                "quarter": quarter,
                "actual_revenue": revenue,
                "projection": round(revenue * factor, 2),
                "status": "draft",
            })
    asset = register(
        manifest,
        asset_id="prerelease_financials",
        in_story_name="Pre-release financials",
        synthetic=True,
        source="synthetic (rolled up from TPC-DS aggregates)",
        provenance_url="",
        scale_badge="≈8 quarters × segments",
        connector="Drive / warehouse",
        vertical="FINANCE",
        retrieval_mode="structured",
        sensitivity_class="E",
        clearance_level=4,  # class E is L4+ (FINANCE/C-suite) — FM sees it (C2 design)
        owner_department="FINANCE",
        fields=(
            FieldSpec("segment", "str"),
            FieldSpec("quarter", "str"),
            FieldSpec("actual_revenue", "float"),
            FieldSpec("projection", "float"),
            FieldSpec("status", "str"),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

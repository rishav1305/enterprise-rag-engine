"""Treasury — cash positions, FX, debt facilities (re-included domain — class N, L5).

Material non-public information; L5 FINANCE/C_SUITE need-to-know.
"""

from __future__ import annotations

from .._coherence import anchors, FISCAL_QUARTERS
from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_CURRENCIES = ["USD", "GBP", "SGD", "BRL", "EUR"]
_INSTRUMENTS = ["cash", "revolver", "term_loan", "bond", "fx_forward"]


def generate(manifest: Manifest, scale: float = 1.0) -> SourceOutput:
    rng = derive_rng("treasury")
    rev = anchors().segment_revenue
    rows = []
    for quarter in FISCAL_QUARTERS:
        total_rev = sum(rev[quarter].values())
        for instrument in _INSTRUMENTS:
            for ccy in _CURRENCIES:
                rows.append({
                    "position_id": f"TRS-{quarter}-{instrument}-{ccy}",
                    "quarter": quarter,
                    "instrument": instrument,
                    "currency": ccy,
                    "notional": round(total_rev * float(rng.np.uniform(0.01, 0.3)), 2),
                    "fx_rate": round(float(rng.np.uniform(0.7, 1.4)), 4),
                })
    asset = register(
        manifest,
        asset_id="treasury_positions",
        in_story_name="Treasury — cash/FX/debt",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈8 quarters × instruments × currencies",
        connector="Treasury system",
        vertical="FINANCE",
        retrieval_mode="structured",
        sensitivity_class="N",
        clearance_level=5,
        owner_department="FINANCE",
        fields=(
            FieldSpec("position_id", "str"),
            FieldSpec("quarter", "str"),
            FieldSpec("instrument", "str"),
            FieldSpec("currency", "str"),
            FieldSpec("notional", "float"),
            FieldSpec("fx_rate", "float"),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

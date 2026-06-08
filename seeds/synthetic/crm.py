"""CRM pipeline (Salesforce) — class D deal-value field-level security; world bible §7."""

from __future__ import annotations

from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_STAGES = ["prospect", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]


def generate(manifest: Manifest, scale: float = 1.0, n_opps: int = 30_000) -> SourceOutput:
    rng = derive_rng("crm")
    n = max(1, int(n_opps * scale))
    rows = []
    for i in range(n):
        rows.append({
            "opportunity_id": f"OPP-{i:06d}",
            "account": rng.faker.company(),
            "stage": _STAGES[int(rng.np.integers(0, len(_STAGES)))],
            "deal_value": int(rng.np.integers(5_000, 2_000_000)),
            "owner": f"EMP-{int(rng.np.integers(0, 12000)):06d}",
        })
    asset = register(
        manifest,
        asset_id="crm_pipeline",
        in_story_name="CRM pipeline",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈30k opportunities",
        connector="CRM (Salesforce)",
        vertical="SALES",
        retrieval_mode="structured",
        sensitivity_class="C",  # team-ops; deal_value is field-level secured (D)
        clearance_level=2,
        owner_department="SALES",
        fields=(
            FieldSpec("opportunity_id", "str"),
            FieldSpec("account", "str"),
            FieldSpec("stage", "str"),
            FieldSpec("deal_value", "int", pii=True, masked=True),  # field-level secured
            FieldSpec("owner", "str"),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

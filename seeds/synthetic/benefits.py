"""Benefits enrollment (re-included domain — class J, L2, PII masked)."""

from __future__ import annotations

from .._coherence import anchors
from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_PLANS = ["HEALTH_PPO", "HEALTH_HMO", "DENTAL", "VISION", "401K", "HSA"]


def generate(manifest: Manifest, scale: float = 1.0) -> SourceOutput:
    rng = derive_rng("benefits")
    org = anchors().org_chart
    n = max(1, int(len(org) * scale))
    rows = []
    for eid in sorted(org)[:n]:
        n_plans = int(rng.np.integers(1, len(_PLANS) + 1))
        idx = sorted(rng.np.choice(len(_PLANS), size=n_plans, replace=False).tolist())
        for i in idx:
            rows.append({
                "enrollment_id": f"BEN-{eid}-{_PLANS[i]}",
                "employee_id": eid,
                "plan": _PLANS[i],
                "dependents": int(rng.np.integers(0, 4)),
                "contribution_pct": round(float(rng.np.uniform(0.0, 0.12)), 3),
            })

    asset = register(
        manifest,
        asset_id="benefits_enrollment",
        in_story_name="Benefits enrollment",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈12k employees",
        connector="HRIS (Workday) / benefits",
        vertical="PEOPLE",
        retrieval_mode="structured",
        sensitivity_class="J",
        clearance_level=4,  # §7: health PII -> L4 + HR need-to-know
        owner_department="PEOPLE",
        fields=(
            FieldSpec("enrollment_id", "str"),
            FieldSpec("employee_id", "str", pii=True, masked=True),
            FieldSpec("plan", "str"),
            FieldSpec("dependents", "int", pii=True, masked=True),
            FieldSpec("contribution_pct", "float"),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

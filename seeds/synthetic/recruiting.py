"""Recruiting / ATS (re-included domain — class K, L3; offer comp L4).

Candidate PII masked; offers reference valid open reqs (coherence).
"""

from __future__ import annotations

from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_STAGES = ["applied", "screen", "onsite", "offer", "hired", "rejected"]
_DEPTS = ["ENGINEERING", "SALES", "FINANCE", "MARKETING", "COMMERCE"]


def generate(manifest: Manifest, scale: float = 1.0, n_reqs: int = 200) -> SourceOutput:
    rng = derive_rng("recruiting")
    n_reqs = max(1, int(n_reqs * scale))
    # open reqs first (so candidates reference valid ones)
    reqs = [f"REQ-{i:05d}" for i in range(n_reqs)]
    rows = []
    cand_per_req = 8
    for r in reqs:
        dept = _DEPTS[int(rng.np.integers(0, len(_DEPTS)))]
        for c in range(cand_per_req):
            stage = _STAGES[int(rng.np.integers(0, len(_STAGES)))]
            offer_comp = (
                int(120_000 + rng.np.integers(0, 180_000)) if stage in ("offer", "hired") else None
            )
            rows.append({
                "candidate_id": f"CAND-{r}-{c:02d}",
                "req_id": r,
                "dept": dept,
                "candidate_name": rng.faker.name(),
                "stage": stage,
                "offer_comp": offer_comp,
            })

    asset = register(
        manifest,
        asset_id="recruiting_ats",
        in_story_name="Recruiting / ATS",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge=f"≈{n_reqs} reqs × {cand_per_req} candidates",
        connector="ATS (Greenhouse)",
        vertical="PEOPLE",
        retrieval_mode="vector",
        sensitivity_class="K",
        clearance_level=3,
        owner_department="PEOPLE",
        fields=(
            FieldSpec("candidate_id", "str"),
            FieldSpec("req_id", "str"),
            FieldSpec("dept", "str"),
            FieldSpec("candidate_name", "str", pii=True, masked=True),
            FieldSpec("stage", "str"),
            FieldSpec("offer_comp", "int", pii=True, masked=True),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

"""Expense reports (re-included domain — class L, L2; exec expenses escalate)."""

from __future__ import annotations

from .._coherence import anchors
from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_CATEGORIES = ["travel", "meals", "software", "hardware", "events", "training"]


def generate(manifest: Manifest, scale: float = 1.0, n_reports: int = 40_000) -> SourceOutput:
    rng = derive_rng("expenses")
    org = anchors().org_chart
    emp_ids = sorted(org)
    n = max(1, int(n_reports * scale))
    rows = []
    for i in range(n):
        eid = emp_ids[int(rng.np.integers(0, len(emp_ids)))]
        rows.append({
            "report_id": f"EXP-{i:06d}",
            "employee_id": eid,
            "category": _CATEGORIES[int(rng.np.integers(0, len(_CATEGORIES)))],
            "amount": round(float(rng.np.uniform(5.0, 8_000.0)), 2),
            "status": "approved" if rng.np.random() < 0.8 else "pending",
        })
    asset = register(
        manifest,
        asset_id="expense_reports",
        in_story_name="Expense reports",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈40k reports",
        connector="Expense tool (Concur)",
        vertical="FINANCE",
        retrieval_mode="structured",
        sensitivity_class="L",
        clearance_level=2,
        owner_department="FINANCE",
        fields=(
            FieldSpec("report_id", "str"),
            FieldSpec("employee_id", "str", pii=True, masked=True),
            FieldSpec("category", "str"),
            FieldSpec("amount", "float"),
            FieldSpec("status", "str"),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

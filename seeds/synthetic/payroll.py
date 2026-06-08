"""Payroll runs (re-included domain — world bible §7 expanded).

Individual payroll lines are class I (L5, FINANCE/C_SUITE need-to-know); gross
ties to HR comp bands for coherence. Aggregates are L1.
"""

from __future__ import annotations

from .._coherence import anchors
from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_PERIODS = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06"]


def generate(manifest: Manifest, scale: float = 1.0) -> SourceOutput:
    rng = derive_rng("payroll")
    org = anchors().org_chart
    n = max(1, int(len(org) * scale))
    emp_ids = sorted(org)[:n]

    rows = []
    for eid in emp_ids:
        node = org[eid]
        monthly_gross = (80_000 + node.level * 35_000) / 12.0
        bank_acct = rng.faker.iban()  # per-employee; PII, masked (never absent — §10)
        for period in _PERIODS:
            tax_wh = round(monthly_gross * float(rng.np.uniform(0.20, 0.32)), 2)
            net = round(monthly_gross - tax_wh, 2)
            rows.append({
                "payroll_id": f"PR-{eid}-{period}",
                "employee_id": eid,
                "period": period,
                "gross": round(monthly_gross, 2),
                "tax_withheld": tax_wh,
                "net_pay": net,
                "bank_acct": bank_acct,
            })

    asset = register(
        manifest,
        asset_id="payroll_runs",
        in_story_name="Payroll runs",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈12k employees × monthly",
        connector="HRIS (Workday) / payroll",
        vertical="PEOPLE",
        retrieval_mode="structured",
        sensitivity_class="I",
        clearance_level=5,
        owner_department="PEOPLE",
        fields=(
            FieldSpec("payroll_id", "str"),
            FieldSpec("employee_id", "str"),
            FieldSpec("period", "str"),
            FieldSpec("gross", "float", pii=True, masked=True),
            FieldSpec("tax_withheld", "float", pii=True, masked=True),
            FieldSpec("net_pay", "float", pii=True, masked=True),
            FieldSpec("bank_acct", "str", pii=True, masked=True),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

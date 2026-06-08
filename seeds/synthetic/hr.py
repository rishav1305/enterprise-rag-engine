"""HR records + exec comp (world bible §7).

Coherent with the shared org chart (manager_id resolves; execs flagged).
Comp is class F (exec, L5) for the ~120 execs; comp bands / policies are L1.
Volume: ~12k employees (representative slice scaled by ``scale``).
"""

from __future__ import annotations

from .._coherence import anchors
from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_BANDS = ["IC1", "IC2", "IC3", "IC4", "M1", "M2", "DIR", "VP", "SVP", "EXEC"]


def generate(manifest: Manifest, scale: float = 1.0) -> SourceOutput:
    rng = derive_rng("hr")
    org = anchors().org_chart
    exec_set = set(anchors().exec_ids)

    n = max(1, int(len(org) * scale))
    rows = []
    for eid in sorted(org)[:n]:
        node = org[eid]
        is_exec = eid in exec_set
        # salary coheres with seniority/level; deterministic
        base = 80_000 + node.level * 35_000
        salary = int(base + rng.np.integers(0, 40_000))
        if is_exec:
            salary += 250_000
        rows.append({
            "employee_id": eid,
            "full_name": rng.faker.name(),
            "dept": node.dept,
            "band": _BANDS[min(node.level * 2 + (4 if is_exec else 0), len(_BANDS) - 1)],
            "salary": salary,
            "manager_id": node.manager_id or "",
            "is_exec": is_exec,
        })

    asset = register(
        manifest,
        asset_id="hr_records",
        in_story_name="HR records + exec comp",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈12k employees · ~120 execs",
        connector="HRIS (Workday)",
        vertical="PEOPLE",
        retrieval_mode="vector",
        sensitivity_class="F",  # individual comp is exec-comp class
        clearance_level=5,
        owner_department="PEOPLE",
        fields=(
            FieldSpec("employee_id", "str"),
            FieldSpec("full_name", "str", pii=True, masked=True),
            FieldSpec("dept", "str"),
            FieldSpec("band", "str"),
            FieldSpec("salary", "int", pii=True, masked=True),
            FieldSpec("manager_id", "str"),
            FieldSpec("is_exec", "bool"),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

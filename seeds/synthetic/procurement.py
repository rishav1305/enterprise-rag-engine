"""Procurement / supplier graph — the GRAPH leg (world bible §7).

Emits a connected supplier -> contract -> component -> recall edge set for
multi-hop traversal. Supplier list is L1; contract terms L3.
"""

from __future__ import annotations

from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest


def generate(manifest: Manifest, scale: float = 1.0, n_suppliers: int = 2_000,
             n_contracts: int = 8_000, n_components: int = 15_000,
             n_recalls: int = 300) -> SourceOutput:
    rng = derive_rng("procurement")
    ns = max(2, int(n_suppliers * scale))
    nc = max(2, int(n_contracts * scale))
    ncomp = max(2, int(n_components * scale))
    nr = max(1, int(n_recalls * scale))

    suppliers = [f"SUP-{i:05d}" for i in range(ns)]
    contracts = [f"CON-{i:05d}" for i in range(nc)]
    components = [f"CMP-{i:05d}" for i in range(ncomp)]

    rows = []
    # nodes
    for s in suppliers:
        rows.append({"kind": "supplier", "id": s, "name": rng.faker.company()})
    # contract edges: supplier -> contract (each contract belongs to a supplier)
    for c in contracts:
        s = suppliers[int(rng.np.integers(0, ns))]
        rows.append({
            "kind": "contract", "id": c, "supplier_id": s,
            "terms_value": int(rng.np.integers(10_000, 5_000_000)),
        })
    # component edges: contract -> component
    for cmp_ in components:
        c = contracts[int(rng.np.integers(0, nc))]
        rows.append({"kind": "component", "id": cmp_, "contract_id": c,
                     "part": rng.faker.word()})
    # recall edges: component -> recall
    for i in range(nr):
        cmp_ = components[int(rng.np.integers(0, ncomp))]
        rows.append({"kind": "recall", "id": f"REC-{i:04d}", "component_id": cmp_,
                     "reason": rng.faker.sentence(nb_words=6)})

    asset = register(
        manifest,
        asset_id="procurement_graph",
        in_story_name="Procurement / supplier graph",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈2k suppliers · 8k contracts · 15k components · 300 recalls",
        connector="ERP / procurement",
        vertical="MOBILITY_OPS",
        retrieval_mode="graph",
        sensitivity_class="C",  # team-ops L2; contract terms L3 via field ACL (column-level)
        clearance_level=2,      # matches class C min_level (asset-level inherits class)
        owner_department="LEGAL",
        fields=(
            FieldSpec("id", "str"),
            FieldSpec("kind", "str"),
            FieldSpec("supplier_id", "str"),
            FieldSpec("contract_id", "str"),
            FieldSpec("component_id", "str"),
            FieldSpec("terms_value", "int", pii=True, masked=True),  # contract terms L3
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

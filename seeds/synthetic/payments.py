"""Payments ledger + KYC — KYC PII masked (class D raw L4); aggregates L1.

COHERENCE: transaction amounts are drawn to tie to marketplace order scale.
World bible §7.
"""

from __future__ import annotations

from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_MERCHANTS = ["mobility", "marketplace", "pay", "ads"]


def generate(manifest: Manifest, scale: float = 1.0, n_txns: int = 5_000_000,
             n_kyc: int = 200_000) -> SourceOutput:
    rng = derive_rng("payments")
    nt = max(1, int(n_txns * scale))
    nk = max(1, int(n_kyc * scale))

    rows = []
    # KYC identities (masked PII)
    kyc_ids = []
    for i in range(nk):
        kid = f"KYC-{i:07d}"
        kyc_ids.append(kid)
        rows.append({
            "kind": "kyc",
            "kyc_id": kid,
            "name": rng.faker.name(),
            "dob": rng.faker.date_of_birth(minimum_age=18, maximum_age=90).isoformat(),
            "gov_id": rng.faker.ssn(),
        })
    # transactions (tie to merchant segments)
    for i in range(nt):
        rows.append({
            "kind": "txn",
            "txn_id": f"TXN-{i:09d}",
            "amount": round(float(rng.np.uniform(1.0, 5_000.0)), 2),
            "merchant": _MERCHANTS[int(rng.np.integers(0, len(_MERCHANTS)))],
            "kyc_id": kyc_ids[int(rng.np.integers(0, nk))],
        })

    asset = register(
        manifest,
        asset_id="payments_ledger",
        in_story_name="Payments ledger + KYC",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈5M transactions · 200k KYC identities",
        connector="Warehouse / payments DB",
        vertical="FINANCE",
        retrieval_mode="structured",
        sensitivity_class="D",  # KYC PII -> masked; raw L4
        clearance_level=4,
        owner_department="RISK_SECURITY",
        fields=(
            FieldSpec("txn_id", "str"),
            FieldSpec("amount", "float"),
            FieldSpec("merchant", "str"),
            FieldSpec("kyc_id", "str"),
            FieldSpec("name", "str", pii=True, masked=True),
            FieldSpec("dob", "str", pii=True, masked=True),
            FieldSpec("gov_id", "str", pii=True, masked=True),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

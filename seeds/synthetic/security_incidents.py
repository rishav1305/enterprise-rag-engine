"""Security incidents — class H (Risk & Security, L4 + CISO/SECURITY/BOARD).

The dedicated class-H estate asset (world bible §3 Risk & Security). Gives the
oracle a real H asset so parity round-trips literally 210/210 through SurrealDB
(previously H was governed only on the seed/oracle side), and gives TurboVec/H a
real vector-mode asset. No PII columns — incident metadata, not personal data.
"""

from __future__ import annotations

from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_SEVERITY = ["sev1", "sev2", "sev3"]
_SYSTEMS = ["auth-gw", "payments", "data-lake", "mesh", "kyc-svc", "edge-cdn"]
_KINDS = ["intrusion_attempt", "data_exfil_alert", "credential_leak",
          "ddos", "policy_violation", "malware_detection"]


def generate(manifest: Manifest, scale: float = 1.0, n_incidents: int = 1_200) -> SourceOutput:
    rng = derive_rng("security_incidents")
    n = max(1, int(n_incidents * scale))
    rows = []
    for i in range(n):
        rows.append({
            "incident_id": f"SEC-{i:05d}",
            "kind": _KINDS[int(rng.np.integers(0, len(_KINDS)))],
            "severity": _SEVERITY[int(rng.np.integers(0, len(_SEVERITY)))],
            "affected_system": _SYSTEMS[int(rng.np.integers(0, len(_SYSTEMS)))],
            "summary": rng.faker.sentence(nb_words=10),
            "status": "open" if rng.np.random() < 0.4 else "resolved",
        })

    asset = register(
        manifest,
        asset_id="security_incidents",
        in_story_name="Security incidents + threat intel",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈1.2k incidents",
        connector="SIEM / Jira",
        vertical="RISK_SECURITY",
        retrieval_mode="vector",
        sensitivity_class="H",
        clearance_level=4,  # class H min_level
        owner_department="RISK_SECURITY",
        fields=(
            FieldSpec("incident_id", "str"),
            FieldSpec("kind", "str"),
            FieldSpec("severity", "str"),
            FieldSpec("affected_system", "str"),
            FieldSpec("summary", "str"),
            FieldSpec("status", "str"),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

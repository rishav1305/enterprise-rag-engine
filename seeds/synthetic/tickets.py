"""Eng/IT incident tickets + error codes + runbooks — the LEXICAL leg.

Stable ticket ids (MER-####) and error codes (ERR-DB-0042) are exact-match
targets for the full-text mode (golden scenario #7). Security-incident tickets
are class H/L3. World bible §7.
"""

from __future__ import annotations

from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_COMPONENTS = ["DB", "API", "AUTH", "CACHE", "QUEUE", "NET", "PAY", "MOBILE"]
_SEVERITY = ["sev1", "sev2", "sev3", "sev4"]


def generate(manifest: Manifest, scale: float = 1.0, n_tickets: int = 50_000,
             n_error_codes: int = 2_000) -> SourceOutput:
    rng = derive_rng("tickets")
    n_codes = max(1, int(n_error_codes * scale))
    n = max(1, int(n_tickets * scale))

    rows = []
    # error codes (the exact-ID targets — incl. the showcase ERR-DB-0042)
    for i in range(n_codes):
        comp = _COMPONENTS[i % len(_COMPONENTS)]
        rows.append({
            "kind": "error_code",
            "error_code": f"ERR-{comp}-{i:04d}",
            "component": comp,
            "description": rng.faker.sentence(nb_words=8),
        })
    # incident tickets
    for i in range(n):
        comp = _COMPONENTS[int(rng.np.integers(0, len(_COMPONENTS)))]
        is_security = comp in ("AUTH", "NET") and rng.np.random() < 0.2
        rows.append({
            "kind": "ticket",
            "ticket_id": f"MER-{i:05d}",
            "error_code": f"ERR-{comp}-{int(rng.np.integers(0, n_codes)):04d}",
            "component": comp,
            "severity": _SEVERITY[int(rng.np.integers(0, len(_SEVERITY)))],
            "is_security": bool(is_security),
            "summary": rng.faker.sentence(nb_words=10),
        })

    asset = register(
        manifest,
        asset_id="it_tickets",
        in_story_name="Eng/IT incident tickets + error codes",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈50k tickets · ~2k error codes",
        connector="Jira/ServiceNow + Confluence",
        vertical="ENGINEERING",
        retrieval_mode="full-text",
        sensitivity_class="C",  # L1-L2; security tickets escalate via ACL to L3
        clearance_level=2,
        owner_department="ENGINEERING",
        fields=(
            FieldSpec("ticket_id", "str"),
            FieldSpec("error_code", "str"),
            FieldSpec("component", "str"),
            FieldSpec("severity", "str"),
            FieldSpec("summary", "str"),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

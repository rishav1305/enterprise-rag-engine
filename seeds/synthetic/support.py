"""Customer support tickets + transcripts — customer PII masked (class D); world bible §7."""

from __future__ import annotations

from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_RESOLUTIONS = ["resolved", "escalated", "pending", "closed_no_response"]


def generate(manifest: Manifest, scale: float = 1.0, n_tickets: int = 30_000) -> SourceOutput:
    rng = derive_rng("support")
    n = max(1, int(n_tickets * scale))
    rows = []
    for i in range(n):
        rows.append({
            "ticket_id": f"SUP-{i:06d}",
            "customer_ref": rng.faker.email(),
            "transcript": rng.faker.paragraph(nb_sentences=3),
            "resolution": _RESOLUTIONS[int(rng.np.integers(0, len(_RESOLUTIONS)))],
        })
    asset = register(
        manifest,
        asset_id="support_tickets",
        in_story_name="Customer support tickets + transcripts",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈30k tickets + transcripts",
        connector="Zendesk / Slack",
        vertical="KNOWLEDGE_SUPPORT",
        retrieval_mode="vector",
        sensitivity_class="D",  # customer PII -> masking leg
        clearance_level=1,
        owner_department="KNOWLEDGE_SUPPORT",
        fields=(
            FieldSpec("ticket_id", "str"),
            FieldSpec("customer_ref", "str", pii=True, masked=True),
            FieldSpec("transcript", "str", pii=True, masked=True),
            FieldSpec("resolution", "str"),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

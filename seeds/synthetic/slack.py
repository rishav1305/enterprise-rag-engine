"""Internal comms (Slack) — channel-scoped ACLs; world bible §7."""

from __future__ import annotations

from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_CHANNELS = [
    ("general", 1), ("eng-platform", 2), ("finance-private", 4),
    ("legal-mna", 5), ("exec-staff", 5), ("support", 1), ("security-incidents", 4),
]


def generate(manifest: Manifest, scale: float = 1.0, n_messages: int = 200_000) -> SourceOutput:
    rng = derive_rng("slack")
    n = max(1, int(n_messages * scale))
    rows = []
    for i in range(n):
        ch, _ = _CHANNELS[int(rng.np.integers(0, len(_CHANNELS)))]
        rows.append({
            "message_id": f"MSG-{i:08d}",
            "channel": ch,
            "user": f"EMP-{int(rng.np.integers(0, 12000)):06d}",
            "ts": 1704067200 + int(rng.np.integers(0, 31_536_000)),
            "text": rng.faker.sentence(nb_words=12),
        })
    asset = register(
        manifest,
        asset_id="slack_messages",
        in_story_name="Internal comms",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈200k messages",
        connector="Messages (Slack)",
        vertical="KNOWLEDGE_SUPPORT",
        retrieval_mode="vector",
        sensitivity_class="C",  # team-ops L2; private channels carry higher class via ACL
        clearance_level=2,      # matches class C min_level (asset-level inherits class)
        owner_department="KNOWLEDGE_SUPPORT",
        fields=(
            FieldSpec("message_id", "str"),
            FieldSpec("channel", "str"),
            FieldSpec("user", "str", pii=True, masked=True),
            FieldSpec("ts", "int"),
            FieldSpec("text", "str"),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

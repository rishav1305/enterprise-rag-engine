"""M&A / litigation memos — class G (Legal/M&A, L4-L5). World bible §7.

Backs golden scenario #6 (M&A targets): Strategist + Legal + C-suite see these;
Sales Manager does not.
"""

from __future__ import annotations

from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_STATUS = ["evaluating", "due_diligence", "term_sheet", "closed", "abandoned"]
_KIND = ["mna_target", "litigation"]


def generate(manifest: Manifest, scale: float = 1.0, n_docs: int = 150) -> SourceOutput:
    rng = derive_rng("legal")
    n = max(1, int(n_docs * scale))
    rows = []
    for i in range(n):
        kind = _KIND[int(rng.np.integers(0, len(_KIND)))]
        rows.append({
            "doc_id": f"LEG-{i:04d}",
            "kind": kind,
            "target": rng.faker.company() if kind == "mna_target" else "",
            "thesis": rng.faker.paragraph(nb_sentences=2),
            "status": _STATUS[int(rng.np.integers(0, len(_STATUS)))],
            "counsel_notes": rng.faker.sentence(nb_words=14),
        })
    asset = register(
        manifest,
        asset_id="legal_memos",
        in_story_name="M&A / litigation memos",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge="≈150 docs",
        connector="Drive",
        vertical="LEGAL",
        retrieval_mode="vector",
        sensitivity_class="G",
        clearance_level=4,
        owner_department="LEGAL",
        fields=(
            FieldSpec("doc_id", "str"),
            FieldSpec("kind", "str"),
            FieldSpec("target", "str"),
            FieldSpec("thesis", "str"),
            FieldSpec("status", "str"),
            FieldSpec("counsel_notes", "str"),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

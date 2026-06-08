"""App/service telemetry logs — the FUNNEL tier-out demo (world bible §7).

Generated large precisely to be tiered/deduped OUT by the funnel (PB->TB story).
A representative slice is materialized in CI; ``full_volume`` documents the
~200M-line production shape. Most of this is cold and NOT indexed.
"""

from __future__ import annotations

from .._rng import derive_rng
from .._base import SourceOutput, register
from ..manifest import FieldSpec, Manifest

_SERVICES = ["api-gw", "auth", "trip-svc", "pay-svc", "ads-svc", "search", "cache"]
_LEVELS = ["DEBUG", "INFO", "WARN", "ERROR"]
FULL_VOLUME = 200_000_000  # documented production shape; never materialized in CI


def generate(manifest: Manifest, scale: float = 1.0, sample_lines: int = 20_000) -> SourceOutput:
    rng = derive_rng("telemetry")
    n = max(1, int(sample_lines * scale))
    rows = []
    for i in range(n):
        svc = _SERVICES[int(rng.np.integers(0, len(_SERVICES)))]
        # heavy duplication on purpose -> dedup/tier-out target
        lvl = _LEVELS[int(rng.np.integers(0, len(_LEVELS)))]
        rows.append({
            "ts": 1704067200 + i,
            "service": svc,
            "level": lvl,
            "trace_id": f"trace-{int(rng.np.integers(0, n // 4 + 1)):08d}",  # repeated traces
            "msg": f"{svc} handled request status={int(rng.np.integers(200, 599))}",
        })
    asset = register(
        manifest,
        asset_id="telemetry_logs",
        in_story_name="App/service telemetry logs",
        synthetic=True,
        source="synthetic",
        provenance_url="",
        scale_badge=f"≈{FULL_VOLUME // 1_000_000}M lines (tiered/deduped out)",
        connector="Data lake",
        vertical="ENGINEERING",
        retrieval_mode="funnel",
        sensitivity_class="C",
        clearance_level=2,
        owner_department="ENGINEERING",
        fields=(
            FieldSpec("ts", "int"),
            FieldSpec("service", "str"),
            FieldSpec("level", "str"),
            FieldSpec("trace_id", "str"),
            FieldSpec("msg", "str"),
        ),
        row_count=len(rows),
    )
    return SourceOutput(asset=asset, rows=rows)

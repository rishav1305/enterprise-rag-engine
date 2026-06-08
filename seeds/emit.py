"""Wave 3 — estate emitter.

Runs all synthetic generators + real fixtures into one manifest, then emits the
artifacts every downstream phase consumes:

  * ``manifest.json``                — catalog + Sources page + funnel badges
  * per-source row files (JSONL)      — store load (P0.2a) / index build (P0.2b)
  * ``oracle.json``                   — personas + access-matrix expectations (leak oracle, P0.1b)
  * ``glossary_truth.json``           — legacy_mart physical->meaning + views (P0.4)
  * ``vector_kb_sample`` marker        — Wikipedia derivative feeds TurboVec (P0.2b)

The STORE TARGET is pluggable (CONFIGURABLE / multi-setup): default is a local
filesystem target so P0.1a is self-contained and byte-reproducible; the
SurrealDB Cloud / self-host target is wired in P0.2a behind the same interface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .access_matrix import CLASSES, evaluate_class
from .manifest import Manifest
from .personas import PERSONAS
from .synthetic import (
    benefits, crm, expenses, financials, hr, legacy_mart, legal, payments,
    payroll, procurement, recruiting, slack, support, tax, telemetry, treasury,
)
from .real.sources import FIXTURES
from .synthetic import tickets


def _synthetic_mods():
    return [
        hr, payroll, benefits, recruiting, crm, slack, support, tickets,
        procurement, legacy_mart, telemetry,
        # finance cluster (depend on _coherence) last
        financials, payments, expenses, tax, treasury, legal,
    ]


def build_estate(scale: float = 1.0) -> tuple[Manifest, dict[str, Any]]:
    """Generate the full estate. Returns (manifest, outputs_by_asset_id)."""
    manifest = Manifest()
    outputs: dict[str, Any] = {}
    for mod in _synthetic_mods():
        out = mod.generate(manifest, scale=scale)
        outputs[out.asset.asset_id] = out
    for fix in FIXTURES:
        out = fix(manifest)
        outputs[out.asset.asset_id] = out
    return manifest, outputs


def build_oracle() -> dict[str, Any]:
    """Persona x sensitivity-class expectation grid — the leak oracle ground truth."""
    grid = {}
    for p in PERSONAS:
        grid[p.key] = {
            cls: evaluate_class(cls, p.clearance_level, p.roles).value
            for cls in CLASSES
        }
    return {
        "personas": {p.key: {"title": p.title, "level": p.clearance_level,
                             "roles": list(p.roles)} for p in PERSONAS},
        "expectations": grid,
    }


def emit(out_dir: str | Path, scale: float = 1.0) -> dict[str, Any]:
    """Emit the estate to a local filesystem target. Returns a summary."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_dir = out_dir / "rows"
    rows_dir.mkdir(exist_ok=True)

    manifest, outputs = build_estate(scale=scale)

    # masking-completeness gate (reviewer item: emit MUST call this)
    violations = manifest.validate_masking()
    if violations:
        raise ValueError(f"masking-policy violations: {violations}")

    # manifest.json (byte-stable)
    (out_dir / "manifest.json").write_text(manifest.to_json())

    # per-source rows (JSONL, deterministic order)
    for asset_id, out in outputs.items():
        if out.rows:
            lines = "\n".join(
                json.dumps(r, sort_keys=True, separators=(",", ":"), default=str)
                for r in out.rows
            )
            (rows_dir / f"{asset_id}.jsonl").write_text(lines)

    # oracle.json
    (out_dir / "oracle.json").write_text(
        json.dumps(build_oracle(), sort_keys=True, separators=(",", ":"))
    )

    # glossary_truth.json (from legacy_mart connection metadata)
    lm = outputs["legacy_mart"]
    (out_dir / "glossary_truth.json").write_text(
        json.dumps(lm.connection, sort_keys=True, separators=(",", ":"))
    )

    return {
        "asset_count": len(manifest.assets),
        "synthetic": sum(1 for a in manifest.assets if a.synthetic),
        "real": sum(1 for a in manifest.assets if not a.synthetic),
        "total_rows": sum(len(o.rows) for o in outputs.values()),
        "out_dir": str(out_dir),
    }

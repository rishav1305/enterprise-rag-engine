"""Load the deterministic P0.1a Meridian estate into a SurrealDB store.

Maps each manifest asset to a SurrealDB ``asset`` row carrying the governance
footprint (sensitivity class, level, owning department) + column masking policy.
Idempotent: re-running upserts by asset_id (no duplicates). The same loader
serves the local self-host instance and SurrealDB Cloud (the store's DSN decides).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from seeds.emit import build_estate  # noqa: E402


def load_estate(store, scale: float = 1.0) -> int:
    """Upsert all catalog assets from the estate into ``store``. Returns count."""
    manifest, _ = build_estate(scale=scale)
    n = 0
    for a in manifest.assets:
        store.upsert_asset(
            {
                "asset_id": a.asset_id,
                "cls": a.sensitivity_class,
                "level": a.clearance_level,
                "vertical": a.vertical,
                "retrieval_mode": a.retrieval_mode,
                "owner_department": a.owner_department,
                "synthetic": a.synthetic,
                "columns": [
                    {"name": f.name, "pii": f.pii, "masked": f.masked}
                    for f in a.fields
                ],
            }
        )
        n += 1
    return n

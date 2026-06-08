"""Shared generator contract.

Every synthetic source exposes ``generate(manifest) -> SourceOutput`` and every
real source exposes a ``fixture(manifest) -> SourceOutput`` (no bulk pull). Both
register their ``AssetSpec`` into the shared manifest and return their rows
(synthetic) or sample rows + connection metadata (real).

Rows are plain dicts with deterministic ordering so the reproducibility gate can
hash them stably.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .manifest import AssetSpec, Manifest


@dataclass(slots=True)
class SourceOutput:
    asset: AssetSpec
    rows: list[dict[str, Any]] = field(default_factory=list)
    # for real sources: connection metadata, never bulk data
    connection: dict[str, Any] = field(default_factory=dict)

    def row_hash(self) -> str:
        """Stable hash of the emitted rows (determinism gate)."""
        payload = json.dumps(self.rows, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def register(manifest: Manifest, **kw: Any) -> AssetSpec:
    """Helper: build + register an AssetSpec in one call."""
    return manifest.register(AssetSpec(**kw))

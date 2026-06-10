"""CDC change-event model (P0.9 T2).

A ``ChunkChangeEvent`` is the unit the ``CdcProcessor`` applies. ``source_version``
is a monotonic per-source ordering token: the processor tracks the last-applied
version per chunk and DROPS any event whose version is not strictly newer — which
makes processing both idempotent (replay = no-op) and ordering-safe (a stale event
can't overwrite a newer state).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ChangeOp(str, Enum):
    INSERT = "insert"
    UPDATE = "update"          # text/content change (same governance)
    DELETE = "delete"
    RECLASSIFY = "reclassify"  # sensitivity_class / ACL change (governance change)


@dataclass(frozen=True, slots=True)
class ChunkChangeEvent:
    op: ChangeOp
    chunk_id: str
    source_version: int
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source_version < 0:
            raise ValueError(
                f"source_version must be >= 0 (monotonic), got {self.source_version}"
            )

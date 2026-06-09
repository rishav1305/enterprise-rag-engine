"""Stable, collision-free uint64 <-> chunk record-id bijection for TurboVec.

``IdMapIndex`` keys vectors by ``uint64`` external ids; our chunks are keyed by
SurrealDB string record-ids (``chunk:...``). A pure hash → uint64 risks
collisions; instead we assign an incrementing uint64 on first sight and persist
the mapping alongside the index, so a reloaded index resolves ids exactly.
"""

from __future__ import annotations

_U64_MAX = 2**64


class IdMap:
    def __init__(self) -> None:
        self._fwd: dict[str, int] = {}
        self._rev: dict[int, str] = {}
        self._next: int = 1  # reserve 0; ids are 1-based

    def to_u64(self, chunk_id: str) -> int:
        """Return the stable uint64 for ``chunk_id``, assigning one on first sight."""
        u = self._fwd.get(chunk_id)
        if u is None:
            u = self._next
            if u >= _U64_MAX:  # pragma: no cover - astronomically unreachable
                raise OverflowError("IdMap exhausted the uint64 keyspace")
            self._next += 1
            self._fwd[chunk_id] = u
            self._rev[u] = chunk_id
        return u

    def to_chunk_id(self, u: int) -> str | None:
        return self._rev.get(u)

    def __len__(self) -> int:
        return len(self._fwd)

    def to_dict(self) -> dict[str, object]:
        # serialize the forward map + the next counter (reverse is derived on load)
        return {"fwd": dict(self._fwd), "next": self._next}

    @classmethod
    def from_dict(cls, blob: dict[str, object]) -> "IdMap":
        m = cls()
        m._fwd = dict(blob["fwd"])  # type: ignore[arg-type]
        m._rev = {int(v): k for k, v in m._fwd.items()}
        m._next = int(blob["next"])  # type: ignore[arg-type]
        return m

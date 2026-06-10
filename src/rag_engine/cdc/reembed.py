"""ReEmbedder — version-bump re-embedding that PRESERVES governance (P0.9 WORKER-C).

Re-embedding (a new embedding model / dimensionality) must change ONLY the vector
+ the embedder_version — never the chunk's GOVERNANCE-BEARING stored fields. If a
re-embed dropped/altered one, governance would silently change under a routine
migration. So the ReEmbedder recomputes ``vec`` from the chunk's existing ``text``
and writes it back with the SAME stored fields.

What actually governs a chunk: the stored ``cls`` (sensitivity class) and ``level``
(clearance) are the governance-bearing columns. ``allowed_roles`` and
``need_to_know_roles`` are NOT persisted on the chunk row — they are DERIVED from
``cls`` via ``_CLASS_ROLES`` at allowlist time (see ``chunk_source._security``). So
preserving ``cls`` + ``level`` preserves the FULL governance decision; there are no
separate role columns to drop. ``_PRESERVED`` therefore lists only the fields that
genuinely exist on a chunk row, so the set never claims a guarantee it can't enforce.

Resumable + bounded: it processes only rows still on ``old_version`` (so a crashed
run resumes by re-querying the remaining old-version rows) in batches. On completion
it calls ``cache.invalidate_version(old_version)`` so cache entries embedded under the
old version miss (ties to the P0.7 invalidate_version seam).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from ..retrieval.base import Embedder

_log = logging.getLogger(__name__)

# Stored fields that MUST survive a re-embed unchanged — ONLY the columns that
# actually exist on a chunk row. cls + level are the governance-bearing fields
# (allowed_roles / need_to_know_roles are cls-DERIVED at allowlist time, not
# persisted, so there is nothing role-shaped to preserve here). asset_id is the
# structured-mode key; text is the source the new vector is recomputed from.
_PRESERVED = ("chunk_id", "asset_id", "cls", "level", "text")


class _Store(Protocol):
    def chunks_by_version(self, embedder_version: str) -> list[dict]: ...
    def upsert_chunk(self, chunk: dict) -> None: ...


class _VersionCache(Protocol):
    def invalidate_version(self, stale_version: str) -> None: ...


class ReEmbedder:
    def __init__(
        self,
        store: _Store,
        embedder: Embedder,
        new_version: str,
        cache: _VersionCache | None = None,
        batch_size: int = 128,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.new_version = new_version
        self.cache = cache
        self.batch_size = batch_size

    def reembed_all(self, old_version: str) -> int:
        """Re-embed every chunk still on ``old_version``. Returns the count migrated.

        Resumable: re-queries the remaining old-version rows each batch, so a
        partial run can be re-invoked to finish. Bounded by ``batch_size``.
        """
        migrated = 0
        while True:
            rows = self.store.chunks_by_version(old_version)
            if not rows:
                break
            batch = rows[: self.batch_size]
            for row in batch:
                self._reembed_row(row)
                migrated += 1
            if len(rows) <= self.batch_size:
                break
        # invalidate cache entries embedded under the now-stale version.
        if self.cache is not None and migrated:
            self.cache.invalidate_version(old_version)
        return migrated

    def _reembed_row(self, row: dict[str, Any]) -> None:
        chunk_id = _bare(row.get("id", row.get("chunk_id")))
        text = row.get("text", "")
        new_vec = [float(x) for x in self.embedder.embed([text])[0]]
        # rebuild the row PRESERVING all governance/identity fields; change ONLY the
        # vector + the version. (Copy preserved fields explicitly so a stray/extra
        # field can't smuggle a governance change in.)
        new_row: dict[str, Any] = {k: row[k] for k in _PRESERVED if k in row}
        new_row["chunk_id"] = chunk_id
        new_row["vec"] = new_vec
        new_row["embedder_version"] = self.new_version
        self.store.upsert_chunk(new_row)


def _bare(rid: Any) -> str:
    """Bare chunk key from a SurrealDB id.

    A SurrealDB ``RecordID`` exposes the clean key on ``.id`` — use it. ``str(rid)``
    angle-bracket-wraps keys with special chars (e.g. ``chunk:⟨doc:1⟩``), so naive
    string-splitting corrupts ids like ``doc:1``. Fall back to a split only for a
    plain ``table:key`` string.
    """
    key = getattr(rid, "id", None)
    if key is not None:
        return str(key)
    s = str(rid)
    return s.split(":", 1)[1] if ":" in s else s


__all__ = ["ReEmbedder"]

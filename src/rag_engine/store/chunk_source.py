"""SurrealChunkSource — the production ChunkSource over SurrealDB (P0.2d).

Satisfies the P0.2c ``ChunkSource`` protocol so ``TurboVecRetriever`` hydrates +
derives its allowlist from the REAL store (not in-memory doubles):

  * ``get_chunk(id)``          — full chunk (text + SecurityContext) for the final set.
  * ``all_chunk_security()``   — lightweight chunks (id + SecurityContext, no text/
                                 vec) for the allowlist pass. ELASTIC: the scan
                                 projects ids+ACLs only, never the content/vector blobs.

``SecurityContext`` is rebuilt from the stored ``cls``/``level`` using the SAME
``_CLASS_ROLES`` the catalog connector uses — single governance source, no drift.
"""

from __future__ import annotations

from ..catalog.connector import _CLASS_ROLES
from ..schemas import EnrichedChunk, SecurityContext


def _bare_id(rid) -> str:
    """Extract the bare record key from a SurrealDB RecordID (or str).

    A ``RecordID`` exposes the unescaped key via ``.id`` (e.g. 'hr_records-000000').
    Note: ``str(RecordID)`` angle-bracket-wraps keys with special chars, so we must
    use ``.id`` — not the stringified form — to round-trip the key.
    """
    key = getattr(rid, "id", None)
    if key is not None and not isinstance(rid, str):
        return str(key)
    s = str(rid)
    return s.split(":", 1)[1] if ":" in s else s


def _security(cls: str, level: int) -> SecurityContext:
    """Rebuild a SecurityContext from a stored chunk's cls/level — FAIL-CLOSED.

    The `chunk` table is SCHEMALESS (no ASSERT on `cls`), so a malformed/unknown
    class could otherwise slip through. We index `_CLASS_ROLES[cls]` (NOT
    `.get(cls, [])`) to match ingestion (`catalog.connector`): an unknown class
    raises ``KeyError`` rather than producing empty roles, which `access.evaluate`
    would treat as level-only and ALLOW (a fail-OPEN governance hole). Callers
    decide how to surface the failure (drop the row / return None) — but a row
    with an unknown class must NEVER be admitted.

    NB: ``owner_department`` is intentionally NOT rebuilt here — governance reads
    it nowhere (access-inert); it is dropped on purpose, not an oversight.
    """
    roles = _CLASS_ROLES[cls]  # fail-closed: KeyError on unknown class
    return SecurityContext(
        allowed_roles=roles,
        clearance_level=level,
        sensitivity_class=cls,
        need_to_know_roles=roles,
    )


class SurrealChunkSource:
    def __init__(self, store) -> None:
        self.store = store

    def get_chunk(self, chunk_id: str) -> EnrichedChunk | None:
        row = self.store.get_chunk_row(chunk_id)
        if row is None:
            return None
        try:
            security = _security(row["cls"], row["level"])
        except KeyError:
            # malformed row (unknown/missing class) -> NOT retrievable (fail-closed).
            return None
        cid = _bare_id(row.get("id", chunk_id))
        return EnrichedChunk(
            chunk_id=cid,
            parent_doc_id=row.get("asset_id", ""),
            parent_title=row.get("asset_id", ""),
            content=row.get("text", ""),
            security=security,
        )

    def all_chunk_security(self) -> list[EnrichedChunk]:
        """ELASTIC: ids + ACLs only (content=''), no text/vec pulled.

        Fail-closed: a row with an unknown/missing class is SKIPPED (not added to
        the allowlist), so it is never retrievable. One malformed row cannot make
        the allowlist permissive, nor abort the whole build.
        """
        out: list[EnrichedChunk] = []
        for row in self.store.chunk_security_rows():
            try:
                security = _security(row["cls"], row["level"])
            except KeyError:
                continue  # malformed row -> excluded from the allowlist (fail-closed)
            out.append(
                EnrichedChunk(
                    chunk_id=_bare_id(row["id"]),
                    parent_doc_id=row.get("asset_id", ""),
                    parent_title="",
                    content="",  # NO content pulled
                    security=security,
                )
            )
        return out

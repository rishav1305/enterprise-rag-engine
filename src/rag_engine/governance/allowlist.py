"""Derive the permission allowlist for the vector PRE-filter (P0.2b).

The allowlist is the set of chunk ids a session is cleared to retrieve. It is the
at-scale evolution of the post-filter: instead of retrieving everything and
dropping after, we hand TurboVec only the ids the session may see, so an
unauthorized vector is never even a candidate (drop-before-search).

Consistency invariant: an id is on the allowlist iff the governance decision is
NOT ``deny`` — i.e. allow/mask/partial are retrievable (mask/partial still get
their content redacted downstream by the C1 enforcement). This keeps the
pre-filter and the post-filter in exact agreement.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..schemas import EnrichedChunk, Session
from . import access


def authorized_chunk_ids(session: Session, chunks: Iterable[EnrichedChunk]) -> list[str]:
    """Return the chunk ids ``session`` may retrieve (decision != deny).

    Order-preserving and deterministic.
    """
    out: list[str] = []
    for chunk in chunks:
        if access.evaluate(chunk, session).decision != "deny":
            out.append(chunk.chunk_id)
    return out

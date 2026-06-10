"""Derive the permission allowlist for retrieval PRE-filters (P0.2b, P0.6).

The allowlist is the set of chunk ids a session is cleared to retrieve. It is the
at-scale evolution of the post-filter: instead of retrieving everything and
dropping after, we hand the index only the ids the session may see, so an
unauthorized item is never even a candidate (drop-before-search). P0.2b wired
this for the vector mode; P0.6 extends it to graph / structured / lexical modes
and makes the allowlist *engine* swappable (in-process default + ReBAC backends).

Consistency invariant: an id is on the allowlist iff the governance decision is
NOT ``deny`` — i.e. allow/mask/partial are retrievable (mask/partial still get
their content redacted downstream by the C1 enforcement). This keeps the
pre-filter and the post-filter in exact agreement.

P0.6 — backend ABC. ``AllowlistBackend`` is the swappable engine. ``InProcessAllowlist``
is the DEFAULT + zero-dep fallback: it computes the set by scanning candidates and
calling ``access.evaluate`` (the canonical decision). ReBAC backends (SpiceDB, Oso)
live in ``governance.rebac`` and MUST return the exact same set as ``InProcessAllowlist``
(parity-tested) — the optimization is sub-linear lookup, never a different decision.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from ..schemas import EnrichedChunk, Session
from . import access


@runtime_checkable
class AllowlistBackend(Protocol):
    """Swappable engine that decides which chunk ids a session may retrieve.

    The contract (parity invariant): for any ``session`` and ``candidates``,
    ``authorized_ids`` MUST return exactly the ids whose governance decision is
    NOT ``deny`` under ``access.evaluate`` — order-preserving over ``candidates``.
    A backend that returns a different set is a security defect (a superset leaks;
    a subset over-denies). ``InProcessAllowlist`` is the reference implementation;
    every other backend is parity-tested against it.
    """

    def authorized_ids(
        self, session: Session, candidates: Iterable[EnrichedChunk]
    ) -> list[str]:
        ...


class InProcessAllowlist:
    """Reference allowlist backend — the DEFAULT and zero-dep fallback.

    O(N) scan over candidates calling ``access.evaluate``. This is the canonical
    decision source; ReBAC backends exist to make this lookup sub-linear at scale
    but must agree with it exactly.
    """

    def authorized_ids(
        self, session: Session, candidates: Iterable[EnrichedChunk]
    ) -> list[str]:
        out: list[str] = []
        for chunk in candidates:
            if access.evaluate(chunk, session).decision != "deny":
                out.append(chunk.chunk_id)
        return out


# Module-level default backend. Callers that don't inject a backend get the
# zero-dep in-process engine. ReBAC backends are opt-in (constructed explicitly).
_DEFAULT_BACKEND: AllowlistBackend = InProcessAllowlist()


def authorized_chunk_ids(
    session: Session,
    chunks: Iterable[EnrichedChunk],
    backend: AllowlistBackend | None = None,
) -> list[str]:
    """Return the chunk ids ``session`` may retrieve (decision != deny).

    Order-preserving and deterministic. Back-compat thin wrapper over the
    swappable backend; defaults to the in-process engine. Pass ``backend`` to use
    a ReBAC engine (its result is parity-guaranteed to equal the default's).
    """
    return (backend or _DEFAULT_BACKEND).authorized_ids(session, chunks)

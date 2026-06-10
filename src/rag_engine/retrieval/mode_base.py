"""Shared base for the P0.6 non-vector mode retrievers (graph / structured / lexical).

Each mode mirrors the TurboVecRetriever discipline: derive the per-session
ALLOWLIST from governance (decision != deny), then run the mode's store query
WITH that allowlist so a denied item is never a candidate (drop-before-search).
The pipeline's L5 SecurityFilter (C1 masking) still runs as the second gate
(defense in depth) — the pre-filter drops *denied*, the post-filter *masks*
mask/partial.

The store dependency is a narrow Protocol (the three SurrealStore methods from
Task 1) so each mode is unit-testable against a fake store + the REAL allowlist,
and integration-testable against the live SurrealStore.
"""

from __future__ import annotations

from typing import Protocol

from ..governance.allowlist import AllowlistBackend, authorized_chunk_ids
from ..schemas import EnrichedChunk, Session


class ModeStore(Protocol):
    """The allowlist-scoped per-mode query surface (SurrealStore Task 1 methods)."""

    def graph_neighbors(self, node_chunk_id: str, allow: list[str]) -> list[dict]: ...
    def structured_rows(self, asset_id: str, allow: list[str]) -> list[dict]: ...
    def fulltext_search(self, query: str, allow: list[str]) -> list[dict]: ...


class AclSource(Protocol):
    """Source of the chunk ACLs the allowlist is derived from."""

    def all_chunk_security(self) -> list[EnrichedChunk]: ...


def session_allowlist(
    session: Session,
    source: AclSource,
    backend: AllowlistBackend | None = None,
) -> list[str]:
    """Per-session allowlist (chunk ids, decision != deny) for a non-vector mode.

    Routed through the swappable backend so graph/structured/lexical modes get the
    sub-linear ReBAC engine for free when one is configured — and the SAME set the
    vector mode uses (one governance source, no per-mode drift).
    """
    return authorized_chunk_ids(session, source.all_chunk_security(), backend=backend)

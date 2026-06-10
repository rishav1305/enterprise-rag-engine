"""WORKER-A — Graph retrieval mode with the governance allowlist PRE-filter (P0.6).

Graph traversal (SurrealDB ``->links->`` over chunks) must not return nodes the
session can't see: a denied node is never traversed-to. We derive the per-session
allowlist and hand it to ``store.graph_neighbors(node, allow)`` so the exclusion
happens AT the traversal query (drop-before-search), not in a post-filter a caller
could forget.
"""

from __future__ import annotations

from ..governance.allowlist import AllowlistBackend
from ..schemas import Session
from .mode_base import AclSource, ModeStore, session_allowlist


class GraphRetriever:
    def __init__(
        self,
        store: ModeStore,
        source: AclSource,
        backend: AllowlistBackend | None = None,
    ) -> None:
        self.store = store
        self.source = source
        self.backend = backend

    def retrieve_for_session(
        self, node_chunk_id: str, session: Session
    ) -> list[dict]:
        """Allowlist-scoped graph neighbours of ``node_chunk_id`` for ``session``.

        Returns the raw neighbour rows (chunk ids + fields); a denied neighbour is
        never present. Fail-closed: empty allowlist -> no traversal results.
        """
        allow = session_allowlist(session, self.source, self.backend)
        if not allow:
            return []
        return self.store.graph_neighbors(node_chunk_id, allow)

"""WORKER-C — Lexical/full-text retrieval mode with the allowlist PRE-filter (P0.6).

SurrealDB BM25 full-text search must not surface hits on content the session
can't see. We derive the per-session allowlist and hand it to
``store.fulltext_search(query, allow)`` so a full-text match on a denied chunk is
never a candidate (drop-before-search), not dropped post-hoc.
"""

from __future__ import annotations

from ..governance.allowlist import AllowlistBackend
from ..schemas import Session
from .mode_base import AclSource, ModeStore, session_allowlist


class LexicalRetriever:
    def __init__(
        self,
        store: ModeStore,
        source: AclSource,
        backend: AllowlistBackend | None = None,
    ) -> None:
        self.store = store
        self.source = source
        self.backend = backend

    def retrieve_for_session(self, query: str, session: Session) -> list[dict]:
        """Allowlist-scoped BM25 full-text hits for ``query`` and ``session``.

        A full-text hit on denied content is never returned. Fail-closed: empty
        allowlist -> no hits.
        """
        allow = session_allowlist(session, self.source, self.backend)
        if not allow:
            return []
        return self.store.fulltext_search(query, allow)

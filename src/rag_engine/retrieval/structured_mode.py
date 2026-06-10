"""WORKER-B — Structured/SQL retrieval mode with the allowlist PRE-filter (P0.6).

SurrealQL (and the warehouse path) must not return rows from assets/chunks the
session can't access. We derive the per-session allowlist and hand it to
``store.structured_rows(asset, allow)`` so a denied asset's rows are NEVER
returned — at query time, before (and independent of) the P0.3b text-to-SQL
result-masking that still applies downstream (defense in depth).
"""

from __future__ import annotations

from ..governance.allowlist import AllowlistBackend
from ..schemas import Session
from .mode_base import AclSource, ModeStore, session_allowlist


class StructuredRetriever:
    def __init__(
        self,
        store: ModeStore,
        source: AclSource,
        backend: AllowlistBackend | None = None,
    ) -> None:
        self.store = store
        self.source = source
        self.backend = backend

    def retrieve_for_session(self, asset_id: str, session: Session) -> list[dict]:
        """Allowlist-scoped structured rows for ``asset_id`` and ``session``.

        Rows from a denied asset/chunk are excluded at query time. Fail-closed:
        empty allowlist -> no rows.
        """
        allow = session_allowlist(session, self.source, self.backend)
        if not allow:
            return []
        return self.store.structured_rows(asset_id, allow)

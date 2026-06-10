"""AuthScope — the permission boundary baked into the cache key (P0.7 T0).

A semantic cache keyed only on query similarity is a permission bypass: it would
serve one session's cached answer to another session that isn't cleared for the
content. ``AuthScope`` captures the session's GOVERNANCE-RELEVANT identity —
``clearance_level`` + the SET of ``roles`` — which is exactly what
``governance.access.evaluate`` consults (need-to-know is per-chunk, matched
against these roles). Two sessions with the same AuthScope are governance-
equivalent; a different AuthScope yields a different ``fingerprint()`` so its cache
lookups can never collide with another scope's entries.

The scope is the FIRST of the two cache defenses; the second is re-governing the
stored payload on every hit (``SemanticCache``). Either alone closes the leak;
together they are defense in depth.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..schemas import Session


@dataclass(frozen=True, slots=True)
class AuthScope:
    """Frozen, hashable governance identity: clearance + sorted role tuple."""

    clearance_level: int
    roles: tuple[str, ...]   # SORTED + de-duplicated -> order-independent

    @classmethod
    def from_session(cls, session: Session) -> "AuthScope":
        # session.roles are already upper-cased by the Session validator; sort +
        # dedupe so role ORDER never changes the scope (a set, not a list).
        roles = tuple(sorted(set(session.roles)))
        return cls(clearance_level=session.clearance_level, roles=roles)

    def fingerprint(self) -> str:
        """Stable sha256 hex of the scope — the cache-key namespace per scope.

        Uses a delimiter that can't appear in a role/level so distinct scopes can't
        alias (e.g. roles=['AB'] vs ['A','B']).
        """
        payload = f"L{self.clearance_level}\x1f" + "\x1f".join(self.roles)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

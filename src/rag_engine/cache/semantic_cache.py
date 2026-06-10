"""SemanticCache — the permission-aware semantic answer cache (P0.7 T1).

On a query, if a recent query in the SAME authorization scope is semantically
similar (cosine >= threshold), skip retrieval/generation and reuse the stored
result — but ALWAYS re-apply governance for the requesting session first.

Two layered defenses against a cache-mediated permission bypass:
  1. SCOPE ISOLATION — entries are partitioned by ``AuthScope.fingerprint()``; a
     lookup only ever scans entries with the requester's exact scope. A different
     clearance/role-set cannot reach another scope's entries at all.
  2. RE-GOVERN ON HIT — the stored payload is the chunk ids (+ answer); on a hit
     the supplied ``govern_fn(chunk_ids, session)`` re-derives what the requester
     may see NOW. If that drops chunks, the hit reflects it; if it denies all,
     the hit is downgraded to a MISS (fail-closed — never serve a stale answer
     whose supporting context the caller can no longer see).

Bounded footprint (ELASTIC): per-scope TTL expiry + a global LRU cap on entries.
The embedder is injected (HashingEmbedder by default — deterministic, no creds;
swap for Voyage behind the same ABC, creds-gated, in production).
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..retrieval.base import Embedder
from ..schemas import Session
from .key import AuthScope

_log = logging.getLogger(__name__)

# govern_fn: given the stored chunk ids + the requesting session, return the ids
# the session may retrieve NOW (governance re-applied). The cache never trusts the
# stored authorization — it re-derives it on every hit.
GovernFn = Callable[[Sequence[str], Session], list[str]]


@dataclass(slots=True)
class _Entry:
    query_text: str
    query_vec: np.ndarray
    scope_fp: str
    chunk_ids: list[str]
    answer: str
    created_at: float
    ttl_seconds: float

    def expired(self, now: float) -> bool:
        return (now - self.created_at) > self.ttl_seconds


@dataclass(slots=True)
class CachedResult:
    """What a cache hit returns — re-governed for the requesting session."""

    answer: str
    chunk_ids: list[str]
    similarity: float
    scope_fp: str
    regoverned: bool = True
    metadata: dict = field(default_factory=dict)


class SemanticCache:
    def __init__(
        self,
        embedder: Embedder,
        similarity_threshold: float,
        ttl_seconds: float,
        max_entries: int,
        audit_sink: Any | None = None,
    ) -> None:
        self.embedder = embedder
        self.similarity_threshold = similarity_threshold
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        # audit_sink (optional): on every cache HIT, an attributable `cache_hit`
        # event is recorded (TRANSPARENT — a hit is never an unaudited answer).
        self.audit_sink = audit_sink
        # insertion-ordered for LRU eviction; key -> _Entry. The map is GLOBAL but
        # lookups filter by scope_fp, so scopes are isolated within one store.
        self._entries: "OrderedDict[str, _Entry]" = OrderedDict()
        self._counter = 0

    def _embed(self, query: str) -> np.ndarray:
        return self.embedder.embed([query])[0]

    def get(
        self, query: str, session: Session, govern_fn: GovernFn
    ) -> CachedResult | None:
        """Return a re-governed cache hit for ``query`` under ``session``, or None.

        A hit requires: same auth scope AND cosine >= threshold AND, after
        re-governing the stored chunk ids for this session, at least one chunk
        survives (else fail-closed -> miss).
        """
        scope_fp = AuthScope.from_session(session).fingerprint()
        now = time.monotonic()
        q_vec = self._embed(query)

        best_key: str | None = None
        best_sim = -1.0
        for key, entry in self._entries.items():
            if entry.scope_fp != scope_fp:
                continue  # SCOPE ISOLATION — never cross a permission boundary
            if entry.expired(now):
                continue
            sim = float(np.dot(q_vec, entry.query_vec))  # both L2-normalised
            if sim > best_sim:
                best_sim, best_key = sim, key

        if best_key is None or best_sim < self.similarity_threshold:
            return None

        entry = self._entries[best_key]
        # RE-GOVERN ON HIT — re-derive what this session may see NOW. A govern_fn
        # that RAISES is treated as denial (fail-closed): never serve on an
        # indeterminate governance outcome.
        try:
            authorized = govern_fn(entry.chunk_ids, session)
        except Exception:
            return None
        # MISS-ON-ANY-REDACTION (fail-closed): the stored ANSWER is opaque and was
        # synthesized from the FULL chunk set; we cannot safely re-mask it. So if
        # re-governance changed the authorized set AT ALL (any chunk now denied —
        # not just all of them), MISS and let the pipeline regenerate fresh from the
        # authorized subset. Serving the verbatim answer with merely-trimmed
        # chunk_ids would leak the denied chunk's content. (all-denied is the
        # set-inequality's degenerate case, also a miss.)
        if set(authorized) != set(entry.chunk_ids):
            return None

        self._entries.move_to_end(best_key)  # LRU touch
        self._audit_hit(session, scope_fp, best_sim, len(authorized))
        return CachedResult(
            answer=entry.answer,
            chunk_ids=list(authorized),
            similarity=best_sim,
            scope_fp=scope_fp,
            regoverned=True,
        )

    def _audit_hit(self, session: Session, scope_fp: str, sim: float, n: int) -> None:
        """Record an attributable, metric-only cache_hit event (TRANSPARENT).

        RESILIENT: the audit sink is a SIDE CHANNEL — its failure must not crash a
        cache hit. Carries user_id for attribution + the metric attrs; NO chunk text
        or answer (no-PII contract).
        """
        if self.audit_sink is None:
            return
        from .observability import cache_hit_attributes

        detail = {"user_id": session.user_id, **cache_hit_attributes(sim, scope_fp, n)}
        try:
            self.audit_sink.record_event("cache_hit", detail)
        except Exception:
            _log.exception("cache_hit audit write failed (user=%s) — hit still served",
                           session.user_id)

    def put(
        self,
        query: str,
        session: Session,
        chunk_ids: Sequence[str],
        answer: str,
    ) -> None:
        """Store a governed result for ``query`` under ``session``'s scope."""
        scope_fp = AuthScope.from_session(session).fingerprint()
        self._counter += 1
        key = f"{scope_fp}:{self._counter}"
        self._entries[key] = _Entry(
            query_text=query,
            query_vec=self._embed(query),
            scope_fp=scope_fp,
            chunk_ids=list(chunk_ids),
            answer=answer,
            created_at=time.monotonic(),
            ttl_seconds=self.ttl_seconds,
        )
        self._entries.move_to_end(key)
        self._evict()

    def _evict(self) -> None:
        # Drop expired first (cheap, bounds memory), then LRU over the cap.
        now = time.monotonic()
        for key in [k for k, e in self._entries.items() if e.expired(now)]:
            del self._entries[key]
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)  # evict least-recently-used

    def __len__(self) -> int:
        return len(self._entries)

"""SurrealCacheStore — durable backend for the semantic cache (P0.7 WORKER-D).

The in-memory ``SemanticCache`` is the default; this persists entries to a
SurrealDB ``query_cache`` table so the cache survives a restart and can be shared
across processes (ELASTIC: state lives in the store, the service stays stateless).
Gated like the rest of the SurrealDB paths — the in-memory cache is always tested,
this runs under the ``surreal_local`` fixture / a live DSN.

The permission invariant is IDENTICAL to the in-memory engine and enforced the
same way: entries are namespaced by ``scope_fp`` and a lookup fetches ONLY the
requester's scope, then cosine-matches in-process, then the caller re-governs on
hit. The durable store changes WHERE entries live, never the decision.

Invalidation seam (tracked for P0.9 CDC): on a re-embedding/version bump, entries
are invalidated by deleting rows whose ``embedder_version`` no longer matches —
``invalidate_version`` is the hook; wiring it to the CDC pipeline is the follow-on.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence

import numpy as np

from ..retrieval.base import Embedder
from ..schemas import Session
from .key import AuthScope
from .semantic_cache import CachedResult, GovernFn


class SurrealCacheStore:
    def __init__(
        self,
        store,
        embedder: Embedder,
        similarity_threshold: float,
        ttl_seconds: float,
        embedder_version: str = "hashing-v1",
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.similarity_threshold = similarity_threshold
        self.ttl_seconds = ttl_seconds
        self.embedder_version = embedder_version

    def _embed(self, query: str) -> np.ndarray:
        return self.embedder.embed([query])[0]

    def put(self, query: str, session: Session, chunk_ids: Sequence[str], answer: str) -> None:
        from surrealdb import RecordID

        scope_fp = AuthScope.from_session(session).fingerprint()
        row = {
            "id": uuid.uuid4().hex,
            "scope_fp": scope_fp,
            "query_text": query,
            "query_vec": [float(x) for x in self._embed(query)],
            "chunk_ids": list(chunk_ids),
            "answer": answer,
            "created_at": time.time(),
            "embedder_version": self.embedder_version,
        }
        # RecordID-bound id (SECURE — no injection). scope_fp/vec are data params.
        self.store._db.query(
            "UPSERT $rid CONTENT $data;",
            {"rid": RecordID("query_cache", row["id"]), "data": row},
        )

    def get(self, query: str, session: Session, govern_fn: GovernFn) -> CachedResult | None:
        scope_fp = AuthScope.from_session(session).fingerprint()
        # Fetch ONLY this scope's rows (scope isolation at the query) + version match.
        rows = self.store._db.query(
            "SELECT * FROM query_cache WHERE scope_fp = $fp AND embedder_version = $ev;",
            {"fp": scope_fp, "ev": self.embedder_version},
        )
        rows = list(rows) if rows else []
        if not rows:
            return None

        q_vec = self._embed(query)
        now = time.time()
        best = None
        best_sim = -1.0
        for r in rows:
            if (now - float(r["created_at"])) > self.ttl_seconds:
                continue  # TTL expired
            vec = np.asarray(r["query_vec"], dtype=np.float32)
            sim = float(np.dot(q_vec, vec))   # both L2-normalised
            if sim > best_sim:
                best_sim, best = sim, r

        if best is None or best_sim < self.similarity_threshold:
            return None

        authorized = govern_fn(best["chunk_ids"], session)
        if not authorized:
            return None  # fail-closed re-govern miss
        return CachedResult(
            answer=best["answer"], chunk_ids=list(authorized),
            similarity=best_sim, scope_fp=scope_fp, regoverned=True,
        )

    def invalidate_version(self, stale_version: str) -> None:
        """CDC seam (P0.9): drop entries embedded with a now-stale embedder version."""
        self.store._db.query(
            "DELETE query_cache WHERE embedder_version = $ev;", {"ev": stale_version}
        )

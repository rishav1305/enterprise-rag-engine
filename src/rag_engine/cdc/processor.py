"""CdcProcessor — applies change events to the store + cache (P0.9 T3).

The governance-propagation engine. For each event it updates BOTH the store (so
retrieval + the allowlist reflect the change) AND the cache (so a stale governed
result can't be served):

  * INSERT / UPDATE  -> store.upsert_chunk + cache.invalidate_chunk
  * RECLASSIFY       -> store.upsert_chunk (NEW cls/level) + cache.invalidate_chunk
  * DELETE           -> store.delete_chunk + cache.invalidate_chunk

Why invalidate the cache on EVERY op: a cached answer was computed over the chunk's
OLD text/classification. After an update the text changed; after a reclassify the
governance changed (a stale permissive entry could leak now-restricted content);
after a delete the chunk is gone. Dropping the entries forces a recompute under the
new state — fail-closed.

ORDERING + IDEMPOTENCE: a per-chunk last-applied ``source_version`` is tracked; an
event whose version is not strictly greater is DROPPED (a replay or a stale
out-of-order event is a no-op). So processing is safe under at-least-once delivery
and reordering.

CONTRACT — ``source_version`` MUST be UNIQUE and STRICTLY INCREASING PER EVENT for a
given chunk (not per logical state). The ordering guard is ``<=``-drop, so two
DIFFERENT changes that share a version would have the second silently dropped — and
a same-version reclassify-up would leave the permissive prior state live. The live
CDC source connector (a tracked follow-on) is responsible for minting a monotonic
per-chunk version (e.g. a source LSN / commit timestamp / sequence) on EVERY emitted
event; this is a hard requirement on that connector.

RESILIENT: ``apply`` raising mid-event is retried up to ``max_retries``; a
persistently failing event is recorded as a ``cdc_dropped`` audit event (never
silently lost). TRANSPARENT: every applied/dropped event emits a span + audit.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from .events import ChangeOp, ChunkChangeEvent

_log = logging.getLogger(__name__)


class _Store(Protocol):
    def upsert_chunk(self, chunk: dict) -> None: ...
    def delete_chunk(self, chunk_id: str) -> None: ...


class _Cache(Protocol):
    def invalidate_chunk(self, chunk_id: str) -> None: ...


class CdcProcessor:
    def __init__(
        self,
        store: _Store,
        cache: _Cache,
        max_retries: int = 2,
        audit_sink: Any | None = None,
        tracer: Any | None = None,
        request_id: str = "",
    ) -> None:
        self.store = store
        self.cache = cache
        self.max_retries = max_retries
        self.audit_sink = audit_sink
        self.tracer = tracer
        self.request_id = request_id
        # per-chunk last-applied source_version (ordering + idempotence).
        self._applied_version: dict[str, int] = {}

    def apply(self, event: ChunkChangeEvent) -> bool:
        """Apply one event. Returns True if applied, False if dropped (stale/replay).

        RESILIENT: a transient failure is retried up to max_retries; a persistent
        failure is audited as cdc_dropped and re-raised only after exhausting the
        budget is recorded (so the drop is never silent).
        """
        last = self._applied_version.get(event.chunk_id)
        if last is not None and event.source_version <= last:
            # stale or replayed -> no-op (ordering + idempotence). TRANSPARENT.
            self._emit_span("cdc_skipped_stale", event)
            return False

        attempt = 0
        while True:
            try:
                self._dispatch(event)
                # mark applied only AFTER both store + cache succeeded.
                self._applied_version[event.chunk_id] = event.source_version
                self._audit("cdc_applied", event, attempt=attempt)
                self._emit_span("cdc_applied", event)
                return True
            except Exception:
                attempt += 1
                if attempt > self.max_retries:
                    # bounded retry exhausted -> AUDIT the drop (not silent), re-raise
                    # so the caller/stream can dead-letter it.
                    _log.exception("CDC event failed after %d retries (chunk=%s, op=%s)",
                                   self.max_retries, event.chunk_id, event.op.value)
                    self._audit("cdc_dropped", event, attempt=attempt)
                    self._emit_span("cdc_dropped", event)
                    raise
                _log.warning("CDC event retry %d/%d (chunk=%s)",
                             attempt, self.max_retries, event.chunk_id)

    def _dispatch(self, event: ChunkChangeEvent) -> None:
        if event.op is ChangeOp.DELETE:
            self.store.delete_chunk(event.chunk_id)
        else:
            # insert / update / reclassify all upsert the row with the payload.
            # reclassify carries the NEW cls/level; the store row is the single
            # governance source so the allowlist re-derives the new decision.
            chunk = dict(event.payload)
            chunk["chunk_id"] = event.chunk_id
            self.store.upsert_chunk(chunk)
        # ALWAYS invalidate the cache — any cached result over this chunk is stale
        # (changed text, changed governance, or gone). Fail-closed propagation.
        self.cache.invalidate_chunk(event.chunk_id)

    def _audit(self, kind: str, event: ChunkChangeEvent, attempt: int) -> None:
        if self.audit_sink is None:
            return
        try:
            self.audit_sink.record_event(kind, {
                "chunk_id": event.chunk_id, "op": event.op.value,
                "source_version": event.source_version, "attempt": attempt,
            })
        except Exception:
            _log.exception("CDC audit write failed (chunk=%s) — processing continues",
                           event.chunk_id)

    def _emit_span(self, name: str, event: ChunkChangeEvent) -> None:
        if self.tracer is None:
            return
        with self.tracer.span(name, self.request_id, chunk_id=event.chunk_id,
                              op=event.op.value, source_version=event.source_version):
            pass


__all__ = ["CdcProcessor"]

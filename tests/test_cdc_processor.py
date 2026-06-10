"""WORKER-D — CdcProcessor robustness: idempotence, ordering, RESILIENT, TRANSPARENT.

Replay-safe + ordering-safe under at-least-once/out-of-order delivery; a persistently
failing event is retried with a bounded budget then AUDITED (not silently lost);
every applied/dropped event emits a span + audit.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rag_engine.cdc.events import ChangeOp, ChunkChangeEvent  # noqa: E402
from rag_engine.cdc.processor import CdcProcessor  # noqa: E402
from rag_engine.governance.audit_sink import InMemoryAuditSink  # noqa: E402
from rag_engine.observability.tracer import InMemorySpanCollector, Tracer  # noqa: E402


class _Store:
    def __init__(self):
        self.chunks = {}

    def upsert_chunk(self, chunk):
        self.chunks[chunk["chunk_id"]] = chunk

    def delete_chunk(self, chunk_id):
        self.chunks.pop(chunk_id, None)


class _Cache:
    def invalidate_chunk(self, chunk_id):
        pass


class _FlakyStore(_Store):
    """Fails the first ``fail_times`` upserts, then succeeds."""
    def __init__(self, fail_times):
        super().__init__()
        self.fail_times = fail_times
        self.attempts = 0

    def upsert_chunk(self, chunk):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise RuntimeError("store transient failure")
        super().upsert_chunk(chunk)


def _ev(op, cid, ver, **payload):
    return ChunkChangeEvent(op=op, chunk_id=cid, source_version=ver, payload=payload)


# ---- idempotence + ordering --------------------------------------------
def test_out_of_order_stale_event_dropped():
    p = CdcProcessor(_Store(), _Cache())
    p.apply(_ev(ChangeOp.UPDATE, "c1", 10, text="newest"))
    assert p.apply(_ev(ChangeOp.UPDATE, "c1", 4, text="stale")) is False
    assert p.store.chunks["c1"]["text"] == "newest"


def test_delete_then_reinsert_resurrect_guard():
    # delete (v2) then a NEWER reinsert (v3) resurrects the chunk; a STALE reinsert
    # (v1, pre-delete) is dropped -> a deleted chunk can't be resurrected by replaying
    # an old insert.
    p = CdcProcessor(_Store(), _Cache())
    p.apply(_ev(ChangeOp.INSERT, "c1", 1, cls="B", level=1, text="orig"))
    p.apply(_ev(ChangeOp.DELETE, "c1", 2))
    assert "c1" not in p.store.chunks
    # a stale replay of the original insert (version 1 <= last-applied 2) is dropped
    assert p.apply(_ev(ChangeOp.INSERT, "c1", 1, cls="B", level=1, text="orig")) is False
    assert "c1" not in p.store.chunks                 # NOT resurrected by a stale event
    # a legitimate newer reinsert (version 3) is applied
    assert p.apply(_ev(ChangeOp.INSERT, "c1", 3, cls="B", level=1, text="new")) is True
    assert p.store.chunks["c1"]["text"] == "new"


def test_exact_replay_dropped():
    p = CdcProcessor(_Store(), _Cache())
    ev = _ev(ChangeOp.INSERT, "c1", 1, text="x")
    assert p.apply(ev) is True
    assert p.apply(ev) is False   # same version -> idempotent no-op


# ---- RESILIENT: bounded retry + audited drop ---------------------------
def test_transient_failure_is_retried_then_succeeds():
    audit = InMemoryAuditSink()
    p = CdcProcessor(_FlakyStore(fail_times=2), _Cache(), max_retries=2, audit_sink=audit)
    assert p.apply(_ev(ChangeOp.INSERT, "c1", 1, text="x")) is True
    assert "c1" in p.store.chunks
    assert len(audit.by_kind("cdc_applied")) == 1


def test_persistent_failure_is_audited_then_raised():
    audit = InMemoryAuditSink()
    p = CdcProcessor(_FlakyStore(fail_times=99), _Cache(), max_retries=2, audit_sink=audit)
    with pytest.raises(RuntimeError):
        p.apply(_ev(ChangeOp.INSERT, "c1", 1, text="x"))
    # the drop is AUDITED, not silent
    assert len(audit.by_kind("cdc_dropped")) == 1


def test_failed_event_not_marked_applied():
    # after a persistent failure, the same version must still be re-appliable
    # (it was never recorded as applied).
    store = _FlakyStore(fail_times=3)   # fails 3 then succeeds
    p = CdcProcessor(store, _Cache(), max_retries=1)  # budget 1 -> first call fails
    with pytest.raises(RuntimeError):
        p.apply(_ev(ChangeOp.INSERT, "c1", 5, text="x"))
    # version 5 was never applied -> a re-delivery of version 5 is accepted, not
    # dropped as stale.
    store.fail_times = 0   # store recovers
    assert p.apply(_ev(ChangeOp.INSERT, "c1", 5, text="x")) is True


# ---- TRANSPARENT -------------------------------------------------------
def test_applied_event_emits_span_and_audit():
    collector = InMemorySpanCollector()
    tracer = Tracer(collector=collector, otel=False)
    audit = InMemoryAuditSink()
    p = CdcProcessor(_Store(), _Cache(), audit_sink=audit, tracer=tracer, request_id="r")
    p.apply(_ev(ChangeOp.INSERT, "c1", 1, text="x"))
    assert "cdc_applied" in collector.names()
    assert len(audit.by_kind("cdc_applied")) == 1
    rec = audit.by_kind("cdc_applied")[0]["detail"]
    assert rec["chunk_id"] == "c1" and rec["op"] == "insert"

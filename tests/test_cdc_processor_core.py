"""P0.9 T3 — CdcProcessor core: applies events to store + cache, version-ordered.

Each event updates BOTH the store and the cache (the governance propagation):
insert/update -> upsert_chunk + invalidate_chunk; reclassify -> upsert (new cls) +
invalidate_chunk; delete -> delete_chunk + invalidate_chunk. Version-ordered (stale
dropped), idempotent (replay = no-op). Robustness (retry/audit) is in
test_cdc_processor.py (WORKER-D); governance propagation in WORKER-A/B.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.cdc.events import ChangeOp, ChunkChangeEvent  # noqa: E402
from rag_engine.cdc.processor import CdcProcessor  # noqa: E402


class _FakeStore:
    def __init__(self):
        self.chunks: dict[str, dict] = {}
        self.upserts = 0
        self.deletes = 0

    def upsert_chunk(self, chunk):
        self.upserts += 1
        self.chunks[chunk["chunk_id"]] = chunk

    def delete_chunk(self, chunk_id):
        self.deletes += 1
        self.chunks.pop(chunk_id, None)


class _FakeCache:
    def __init__(self):
        self.invalidated: list[str] = []

    def invalidate_chunk(self, chunk_id):
        self.invalidated.append(chunk_id)


def _proc():
    return CdcProcessor(store=_FakeStore(), cache=_FakeCache())


def _ev(op, cid, ver, **payload):
    return ChunkChangeEvent(op=op, chunk_id=cid, source_version=ver, payload=payload)


def test_insert_upserts_store_and_invalidates_cache():
    p = _proc()
    p.apply(_ev(ChangeOp.INSERT, "c1", 1, cls="B", level=1, text="x"))
    assert "c1" in p.store.chunks
    assert "c1" in p.cache.invalidated   # any cached result over c1 is now stale


def test_delete_removes_from_store_and_invalidates_cache():
    p = _proc()
    p.apply(_ev(ChangeOp.INSERT, "c1", 1, cls="B", level=1, text="x"))
    p.apply(_ev(ChangeOp.DELETE, "c1", 2))
    assert "c1" not in p.store.chunks
    assert p.store.deletes == 1
    assert p.cache.invalidated.count("c1") == 2   # invalidated on insert + delete


def test_reclassify_upserts_new_class_and_invalidates_cache():
    p = _proc()
    p.apply(_ev(ChangeOp.INSERT, "c1", 1, cls="B", level=1, text="secret"))
    p.apply(_ev(ChangeOp.RECLASSIFY, "c1", 2, cls="F", level=5, text="secret"))
    assert p.store.chunks["c1"]["cls"] == "F"     # new classification persisted
    assert p.store.chunks["c1"]["level"] == 5
    assert "c1" in p.cache.invalidated            # stale cache dropped


def test_stale_version_is_dropped():
    p = _proc()
    p.apply(_ev(ChangeOp.INSERT, "c1", 5, cls="B", level=1, text="new"))
    applied = p.apply(_ev(ChangeOp.UPDATE, "c1", 3, cls="B", level=1, text="OLD"))
    assert applied is False                        # version 3 <= last-applied 5 -> dropped
    assert p.store.chunks["c1"]["text"] == "new"   # not overwritten by the stale event


def test_replay_same_event_is_idempotent():
    p = _proc()
    ev = _ev(ChangeOp.INSERT, "c1", 1, cls="B", level=1, text="x")
    assert p.apply(ev) is True
    assert p.apply(ev) is False     # same version -> no-op on replay
    assert p.store.upserts == 1     # applied exactly once


def test_newer_version_wins():
    p = _proc()
    p.apply(_ev(ChangeOp.INSERT, "c1", 1, cls="B", level=1, text="v1"))
    p.apply(_ev(ChangeOp.UPDATE, "c1", 2, cls="B", level=1, text="v2"))
    assert p.store.chunks["c1"]["text"] == "v2"

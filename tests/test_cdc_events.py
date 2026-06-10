"""P0.9 T2 — CDC event model: typed change events with monotonic versioning.

A ChunkChangeEvent carries the op + chunk_id + payload + a monotonic source_version
used for ordering (a stale event whose version <= last-applied is dropped — the
basis for idempotent, ordered processing).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rag_engine.cdc.events import ChunkChangeEvent, ChangeOp  # noqa: E402


def test_event_carries_op_id_version():
    ev = ChunkChangeEvent(op=ChangeOp.INSERT, chunk_id="c1",
                          payload={"cls": "B", "level": 1, "text": "x"},
                          source_version=5)
    assert ev.op is ChangeOp.INSERT
    assert ev.chunk_id == "c1"
    assert ev.source_version == 5


def test_ops_cover_the_lifecycle():
    assert {ChangeOp.INSERT, ChangeOp.UPDATE, ChangeOp.DELETE, ChangeOp.RECLASSIFY} \
        <= set(ChangeOp)


def test_delete_event_needs_no_payload():
    ev = ChunkChangeEvent(op=ChangeOp.DELETE, chunk_id="c1", source_version=2)
    assert ev.payload == {} or ev.payload is None or ev.payload == {}


def test_reclassify_event_carries_new_class():
    ev = ChunkChangeEvent(op=ChangeOp.RECLASSIFY, chunk_id="c1",
                          payload={"cls": "F", "level": 5}, source_version=9)
    assert ev.payload["cls"] == "F"


def test_negative_version_rejected():
    with pytest.raises(ValueError):
        ChunkChangeEvent(op=ChangeOp.INSERT, chunk_id="c1", source_version=-1)

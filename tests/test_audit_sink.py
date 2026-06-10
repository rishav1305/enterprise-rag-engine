"""P0.5 WORKER-C — durable audit sink + chunk_source malformed-row capture."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

pytest.importorskip("surrealdb")

from rag_engine.governance.audit_sink import InMemoryAuditSink  # noqa: E402
from rag_engine.store.chunk_source import SurrealChunkSource  # noqa: E402
from rag_engine.store.surreal import SurrealStore  # noqa: E402


def test_in_memory_audit_sink_records_events():
    sink = InMemoryAuditSink()
    sink.record_event("malformed_chunk_dropped", {"chunk_id": "bad-1", "cls": "ZZ"})
    assert len(sink.events) == 1
    e = sink.by_kind("malformed_chunk_dropped")[0]
    assert e["detail"]["cls"] == "ZZ" and e["ts"] and e["id"]


def test_malformed_drop_captured_in_audit_sink_via_get_chunk(surreal_local):
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db="audit_get",
                      user="root", password="root")
    st.connect()
    st.apply_schema(vector_dim=8)
    st.upsert_chunk({"chunk_id": "bad-1", "asset_id": "bad", "cls": "ZZ",
                     "level": 1, "text": "secret", "vec": [0.0] * 8})
    sink = InMemoryAuditSink()
    source = SurrealChunkSource(st, audit_sink=sink)
    assert source.get_chunk("bad-1") is None             # fail-closed drop
    drops = sink.by_kind("malformed_chunk_dropped")
    assert drops and drops[0]["detail"]["cls"] == "ZZ"   # captured durably
    assert drops[0]["detail"]["where"] == "get_chunk"
    st.close()


def test_malformed_drop_captured_in_allowlist_pass(surreal_local):
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db="audit_allow",
                      user="root", password="root")
    st.connect()
    st.apply_schema(vector_dim=8)
    st.upsert_chunk({"chunk_id": "bad-2", "asset_id": "bad", "cls": "ZZ",
                     "level": 1, "text": "x", "vec": [0.0] * 8})
    st.upsert_chunk({"chunk_id": "good-1", "asset_id": "good", "cls": "B",
                     "level": 1, "text": "y", "vec": [0.0] * 8})
    sink = InMemoryAuditSink()
    source = SurrealChunkSource(st, audit_sink=sink)
    ids = {ec.chunk_id for ec in source.all_chunk_security()}
    assert "bad-2" not in ids and "good-1" in ids        # bad excluded, good kept
    drops = sink.by_kind("malformed_chunk_dropped")
    assert any(d["detail"]["where"] == "all_chunk_security" for d in drops)
    st.close()


def test_no_sink_still_works(surreal_local):
    # audit_sink is optional: without it, the drop still happens (logged only).
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db="audit_none",
                      user="root", password="root")
    st.connect()
    st.apply_schema(vector_dim=8)
    st.upsert_chunk({"chunk_id": "bad-3", "asset_id": "bad", "cls": "ZZ",
                     "level": 1, "text": "x", "vec": [0.0] * 8})
    source = SurrealChunkSource(st)   # no sink
    assert source.get_chunk("bad-3") is None
    st.close()

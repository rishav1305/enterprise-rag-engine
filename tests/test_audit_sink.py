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


# ---- FIX 1: audit sink is a fail-safe side channel (down sink != crashed query) --
class _FailingSink:
    def record_event(self, kind, detail):
        raise RuntimeError("simulated SurrealDB outage")


def test_failing_audit_sink_does_not_crash_get_chunk(surreal_local):
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db="audit_fail_get",
                      user="root", password="root")
    st.connect()
    st.apply_schema(vector_dim=8)
    st.upsert_chunk({"chunk_id": "bad-1", "asset_id": "bad", "cls": "ZZ",
                     "level": 1, "text": "secret", "vec": [0.0] * 8})
    source = SurrealChunkSource(st, audit_sink=_FailingSink())
    # the sink raises, but the request must SURVIVE (the drop still happens)
    assert source.get_chunk("bad-1") is None    # no exception propagated
    st.close()


def test_failing_audit_sink_does_not_crash_allowlist(surreal_local):
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db="audit_fail_allow",
                      user="root", password="root")
    st.connect()
    st.apply_schema(vector_dim=8)
    st.upsert_chunk({"chunk_id": "bad-2", "asset_id": "bad", "cls": "ZZ",
                     "level": 1, "text": "x", "vec": [0.0] * 8})
    st.upsert_chunk({"chunk_id": "good-1", "asset_id": "good", "cls": "B",
                     "level": 1, "text": "y", "vec": [0.0] * 8})
    source = SurrealChunkSource(st, audit_sink=_FailingSink())
    ids = {ec.chunk_id for ec in source.all_chunk_security()}   # no raise
    assert "good-1" in ids and "bad-2" not in ids
    st.close()


# ---- FIX 2: LOCK the no-PII contract on audit records ---------------------------
def test_audit_record_contains_no_chunk_content(surreal_local):
    import json
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db="audit_nopii",
                      user="root", password="root")
    st.connect()
    st.apply_schema(vector_dim=8)
    # seed a dropped chunk whose TEXT is a PII sentinel
    st.upsert_chunk({"chunk_id": "bad-3", "asset_id": "bad", "cls": "ZZ",
                     "level": 1, "text": "SENTINEL_PII_secret@victim.com", "vec": [0.0] * 8})
    sink = InMemoryAuditSink()
    source = SurrealChunkSource(st, audit_sink=sink)
    source.get_chunk("bad-3")
    rec = sink.by_kind("malformed_chunk_dropped")[0]
    # the audit record must carry NO chunk content (only where/chunk_id/cls)
    assert "SENTINEL_PII" not in json.dumps(rec)
    assert set(rec["detail"].keys()) == {"where", "chunk_id", "cls"}
    st.close()

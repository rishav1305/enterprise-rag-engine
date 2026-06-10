"""P0.5 — SurrealAuditSink durability (governance events queryable in SurrealDB)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

pytest.importorskip("surrealdb")

from rag_engine.governance.audit_sink import SurrealAuditSink  # noqa: E402
from rag_engine.store.chunk_source import SurrealChunkSource  # noqa: E402
from rag_engine.store.surreal import SurrealStore  # noqa: E402


def _store(surreal_local, db):
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db=db,
                      user="root", password="root")
    st.connect()
    st.apply_schema(vector_dim=8)
    return st


def test_surreal_audit_sink_persists_and_queries(surreal_local):
    st = _store(surreal_local, "saudit")
    sink = SurrealAuditSink(st)
    sink.record_event("malformed_chunk_dropped", {"chunk_id": "bad-1", "cls": "ZZ"})
    sink.record_event("other_event", {"x": 1})
    rows = sink.query_kind("malformed_chunk_dropped")
    assert len(rows) == 1
    assert rows[0]["detail"]["cls"] == "ZZ"
    st.close()


def test_malformed_drop_durable_via_surreal_sink(surreal_local):
    st = _store(surreal_local, "saudit_drop")
    st.upsert_chunk({"chunk_id": "bad-2", "asset_id": "bad", "cls": "ZZ",
                     "level": 1, "text": "secret", "vec": [0.0] * 8})
    sink = SurrealAuditSink(st)
    source = SurrealChunkSource(st, audit_sink=sink)
    assert source.get_chunk("bad-2") is None
    # the drop is now a DURABLE, queryable SurrealDB record (not just a log line)
    rows = sink.query_kind("malformed_chunk_dropped")
    assert any(r["detail"]["chunk_id"] == "bad-2" for r in rows)
    st.close()

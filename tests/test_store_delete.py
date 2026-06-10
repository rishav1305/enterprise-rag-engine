"""P0.9 T0 — SurrealStore.delete_chunk: a deleted chunk is gone from retrieval.

A deleted chunk must vanish from get_chunk_row, chunk_security_rows (allowlist
source), and all 3 mode queries — RecordID-bound (SECURE). Uses surreal_local;
skips cleanly without the binary/SDK.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _store(surreal_local):
    from rag_engine.store.surreal import SurrealStore
    st = SurrealStore(dsn=surreal_local["dsn"], ns=surreal_local["ns"],
                      db=surreal_local["db"], user=surreal_local["user"],
                      password=surreal_local["pass"])
    st.connect()
    st.apply_schema()
    return st


def _seed(st):
    for cid in ("keep", "drop"):
        st.upsert_chunk({"chunk_id": cid, "asset_id": "a1", "cls": "B", "level": 1,
                         "text": f"meridian {cid} content"})
    st.relate_chunks("keep", "drop")   # an edge to prove edges go too


def test_delete_chunk_removes_from_get_and_security_rows(surreal_local):
    st = _store(surreal_local)
    _seed(st)
    assert st.get_chunk_row("drop") is not None      # present before
    st.delete_chunk("drop")
    assert st.get_chunk_row("drop") is None           # gone after
    ids = {str(r.get("id")) for r in st.chunk_security_rows()}
    assert not any("drop" in i for i in ids)          # gone from allowlist source
    assert any("keep" in i for i in ids)              # the other chunk survives


def test_delete_chunk_removes_from_all_modes(surreal_local):
    st = _store(surreal_local)
    _seed(st)
    st.delete_chunk("drop")
    allow = ["keep", "drop"]   # even if a stale allowlist still names it
    g = {str(r.get("id")) for r in st.graph_neighbors("keep", allow)}
    s = {str(r.get("id")) for r in st.structured_rows("a1", allow)}
    f = {str(r.get("id")) for r in st.fulltext_search("meridian", allow)}
    for result in (g, s, f):
        assert not any("drop" in i for i in result)   # never surfaces in any mode


def test_delete_chunk_is_idempotent(surreal_local):
    st = _store(surreal_local)
    _seed(st)
    st.delete_chunk("drop")
    st.delete_chunk("drop")   # deleting again must not error
    assert st.get_chunk_row("drop") is None

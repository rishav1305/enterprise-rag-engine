"""P0.2d — SurrealChunkSource unit tests (ChunkSource over the real store).

Includes the shared ``_store_with_index`` helper that loads a tiny estate index
into a real SurrealDB instance and returns (store, SurrealChunkSource). The
store-backed E2E (WORKER-B) reuses the same construction pattern.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

pytest.importorskip("turbovec")
pytest.importorskip("surrealdb")

from rag_engine.store.chunk_source import SurrealChunkSource  # noqa: E402
from rag_engine.store.surreal import SurrealStore  # noqa: E402


def _store_with_index(surreal_local, db: str = "cs", dim: int = 128):
    """Build the estate TurboVec index into a real store; return (store, source)."""
    from seeds.targets.turbovec_target import build_index
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db=db,
                      user="root", password="root")
    st.connect()
    st.apply_schema()
    n = build_index(st, out_path=f"/tmp/p0.2d_{db}.tvim", scale=0.01, dim=dim)
    assert n > 0
    return st, SurrealChunkSource(st)


def test_chunksource_get_chunk_roundtrip(surreal_local):
    st, source = _store_with_index(surreal_local, db="cs_roundtrip")
    # pick a real id from the projected rows
    rows = st.chunk_security_rows()
    cid = _bare_id(rows[0]["id"])
    c = source.get_chunk(cid)
    assert c is not None and c.content                  # full text hydrated
    assert c.security.sensitivity_class in set("ABCDEFGHIJKLMN")
    assert source.get_chunk("chunk:does-not-exist") is None
    st.close()


def test_security_context_rebuilt_from_cls_level(surreal_local):
    st, source = _store_with_index(surreal_local, db="cs_sec")
    from rag_engine.catalog.connector import _CLASS_ROLES
    rows = st.chunk_security_rows()
    cid = _bare_id(rows[0]["id"])
    c = source.get_chunk(cid)
    # need-to-know roles match the shared class->roles source (DRY, no drift)
    assert set(c.security.need_to_know_roles) == set(_CLASS_ROLES[c.security.sensitivity_class])
    st.close()


def test_all_chunk_security_is_projection_only(surreal_local):
    st, source = _store_with_index(surreal_local, db="cs_proj")
    rows = source.all_chunk_security()
    assert len(rows) > 0
    for ec in rows:
        assert ec.content == ""                  # NO text pulled (ELASTIC)
        assert "vec" not in ec.metadata          # NO vector pulled
        assert ec.security.sensitivity_class     # ACL present for the allowlist
    # the projected security MATCHES a full get_chunk for the same id
    full = source.get_chunk(rows[0].chunk_id)
    assert full is not None
    assert full.security.clearance_level == rows[0].security.clearance_level
    assert full.security.sensitivity_class == rows[0].security.sensitivity_class
    st.close()


def test_all_chunk_security_covers_every_chunk(surreal_local):
    st, source = _store_with_index(surreal_local, db="cs_cov")
    assert len(source.all_chunk_security()) == st.count_chunks()
    st.close()


def _bare_id(rid) -> str:
    key = getattr(rid, "id", None)
    if key is not None and not isinstance(rid, str):
        return str(key)
    s = str(rid)
    return s.split(":", 1)[1] if ":" in s else s

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


# ---------------------------------------------------------------------------
# WORKER-A additions (P0.2d) — empty-store, class-D, full↔projection parity,
# and the _bare_id special-char round-trip.
# ---------------------------------------------------------------------------


def test_all_chunk_security_empty_store_is_empty_list(surreal_local):
    """A schema'd-but-unseeded store has no chunks → all_chunk_security() == [].

    ``build_index`` always seeds the estate (and asserts n>0), so it can't give us
    an empty store. Instead we stand up a store with the schema applied but NO
    chunks upserted, then wrap it directly. This proves the projection scan returns
    a true empty list (not None, not a sentinel) when the ``chunk`` table is empty —
    the degenerate case the allowlist pass must tolerate.
    """
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db="cs_empty",
                      user="root", password="root")
    st.connect()
    st.apply_schema()
    source = SurrealChunkSource(st)
    assert st.count_chunks() == 0          # precondition: genuinely empty
    result = source.all_chunk_security()
    assert result == []                     # empty list, every chunk covered (zero)
    st.close()


def test_get_chunk_class_d_returns_unmasked_content(surreal_local):
    """A class-D (customer-PII) chunk hydrates with its REAL text + class 'D'.

    Masking is an L5 governance concern, not the store/source's job — the source
    must surface the raw stored text so the masking layer downstream has something
    to redact. We locate a real class-D chunk via the projection, then assert the
    full hydrate carries sensitivity_class 'D' and the actual stored text (which we
    cross-check against the store's own raw row, so this can't pass on an empty
    string).
    """
    st, source = _store_with_index(surreal_local, db="cs_classd")
    d_rows = [r for r in st.chunk_security_rows() if r["cls"] == "D"]
    assert d_rows, "estate must contain at least one class-D vector-mode chunk"
    cid = _bare_id(d_rows[0]["id"])

    c = source.get_chunk(cid)
    assert c is not None
    assert c.security.sensitivity_class == "D"
    # content is the genuine stored text — unmasked at the source (masking is L5).
    raw = st.get_chunk_row(cid)
    assert raw is not None and raw["text"]                  # store actually has text
    assert c.content == raw["text"]                          # source passed it through verbatim
    st.close()


def test_projection_equals_full_for_every_chunk(surreal_local):
    """Load-bearing parity: for EVERY chunk, the lightweight projected ACL ==
    the full-hydrate ACL.

    This is the assertion that proves the ELASTIC ``all_chunk_security`` shortcut
    (no text/vec pulled) didn't silently drop or alter governance data versus the
    full ``get_chunk`` path. We compare class, clearance level, AND need-to-know
    roles across the WHOLE corpus — not just row[0] — so a divergence on any single
    chunk fails the test.
    """
    st, source = _store_with_index(surreal_local, db="cs_parity")
    projected = source.all_chunk_security()
    assert len(projected) == st.count_chunks() > 0           # full coverage, non-trivial

    seen = 0
    for ec in projected:
        full = source.get_chunk(ec.chunk_id)
        assert full is not None, f"projected id {ec.chunk_id!r} not hydratable"
        ps, fs = ec.security, full.security
        assert ps.sensitivity_class == fs.sensitivity_class, ec.chunk_id
        assert ps.clearance_level == fs.clearance_level, ec.chunk_id
        assert set(ps.need_to_know_roles) == set(fs.need_to_know_roles), ec.chunk_id
        seen += 1
    assert seen == len(projected)                            # every row checked, none skipped
    st.close()


def test_bare_id_strips_special_char_wrapping(surreal_local):
    """``_bare_id`` returns the CLEAN record key (via ``.id``), not the
    angle-bracket-wrapped ``str(RecordID)`` form — and that clean key is what
    ``get_chunk`` accepts.

    SurrealDB wraps keys containing special chars (e.g. the '-' in
    'hr_records-000000') as ``chunk:⟨hr_records-000000⟩`` when stringified. If the
    source used ``str(rid)`` it would carry those brackets into every chunk_id and
    break re-lookup. We assert: (a) the bracketed form really differs from the bare
    key, (b) ``_bare_id`` recovers the bare key, and (c) that bare key round-trips
    through ``get_chunk`` against a real stored chunk.
    """
    from rag_engine.store.chunk_source import _bare_id as src_bare_id
    from surrealdb import RecordID

    st, source = _store_with_index(surreal_local, db="cs_bareid")
    # a real stored id that contains the special '-' char
    real_cid = _bare_id(st.chunk_security_rows()[0]["id"])
    assert "-" in real_cid                                    # estate ids are asset_id-ordinal

    rid = RecordID("chunk", real_cid)
    wrapped = str(rid)
    # str(RecordID) wraps special-char keys in angle brackets; the naive
    # split-on-colon path would therefore yield a bracketed (broken) key.
    assert "⟨" in wrapped and "⟩" in wrapped                  # str() genuinely wraps
    assert wrapped != f"chunk:{real_cid}"                     # ...so str-form != bare form
    naive = wrapped.split(":", 1)[1]
    assert naive != real_cid                                  # naive str-split keeps brackets
    assert src_bare_id(rid) == real_cid                       # module export recovers clean key
    assert "⟨" not in src_bare_id(rid) and "⟩" not in src_bare_id(rid)

    # and that clean key is exactly what get_chunk accepts (round-trip).
    c = source.get_chunk(src_bare_id(rid))
    assert c is not None and c.chunk_id == real_cid
    st.close()

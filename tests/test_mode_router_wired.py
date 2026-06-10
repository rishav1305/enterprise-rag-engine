"""P0.11a W4 — ModeRouter wires the 3 mode retrievers + AllowlistBackend, live.

Through a live SurrealDB store: each mode (graph/structured/lexical) pre-filters a
denied chunk for an under-cleared session — the same allowlist drop-before-search the
vector path gets. in_process is the default backend; local_rebac is parity-equal.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.config import EngineConfig  # noqa: E402
from rag_engine.governance.allowlist import InProcessAllowlist  # noqa: E402
from rag_engine.retrieval.mode_router import ModeRouter, build_allowlist_backend  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402
from rag_engine.store.chunk_source import SurrealChunkSource  # noqa: E402


def _store(surreal_local):
    from rag_engine.store.surreal import SurrealStore
    st = SurrealStore(dsn=surreal_local["dsn"], ns=surreal_local["ns"],
                      db=surreal_local["db"], user=surreal_local["user"],
                      password=surreal_local["pass"])
    st.connect()
    st.apply_schema()
    return st


def _seed(st):
    # a public chunk + a DENIED exec-comp chunk (F, NTK C_SUITE, L5), both 'meridian'
    st.upsert_chunk({"chunk_id": "pub", "asset_id": "a1", "cls": "B", "level": 1,
                     "text": "meridian public overview"})
    st.upsert_chunk({"chunk_id": "secret", "asset_id": "a1", "cls": "F", "level": 5,
                     "text": "meridian exec comp secret"})
    st.relate_chunks("pub", "secret")


def test_default_backend_is_in_process():
    assert isinstance(build_allowlist_backend(EngineConfig()), InProcessAllowlist)


def test_local_rebac_backend_selectable(monkeypatch):
    from rag_engine.governance.rebac import LocalReBACAllowlist
    monkeypatch.setenv("RAG_ALLOWLIST_BACKEND", "local_rebac")
    assert isinstance(build_allowlist_backend(EngineConfig()), LocalReBACAllowlist)


def test_all_modes_prefilter_denied_live(surreal_local):
    st = _store(surreal_local)
    _seed(st)
    router = ModeRouter(st, SurrealChunkSource(st), EngineConfig())
    under = Session(user_id="emp", roles=["EMPLOYEE"], clearance_level=2)

    g = {str(r.get("id")) for r in router.graph_neighbors("pub", under)}
    s = {str(r.get("id")) for r in router.structured_rows("a1", under)}
    f = {str(r.get("id")) for r in router.lexical_search("meridian", under)}
    for result in (g, s, f):
        assert not any("secret" in i for i in result), "denied chunk surfaced in a mode"
    # the public chunk IS reachable (structured/lexical return it)
    assert any("pub" in i for i in s) or any("pub" in i for i in f)


def test_local_rebac_router_same_result_as_in_process(surreal_local):
    st = _store(surreal_local)
    _seed(st)
    source = SurrealChunkSource(st)
    under = Session(user_id="emp", roles=["EMPLOYEE"], clearance_level=2)

    cfg_ip = EngineConfig()  # in_process
    import os
    os.environ["RAG_ALLOWLIST_BACKEND"] = "local_rebac"
    try:
        cfg_rebac = EngineConfig()
    finally:
        del os.environ["RAG_ALLOWLIST_BACKEND"]

    ip = {str(r.get("id")) for r in ModeRouter(st, source, cfg_ip).lexical_search("meridian", under)}
    rb = {str(r.get("id")) for r in ModeRouter(st, source, cfg_rebac).lexical_search("meridian", under)}
    assert ip == rb   # parity: the backend changes lookup cost, never the decision

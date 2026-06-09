"""P0.2a — SurrealDB unified store tests (config, schema, store, estate load).

Store tests requiring a live SurrealDB use the session-scoped ``surreal_local``
fixture (ephemeral in-memory instance); they skip cleanly when the binary/SDK is
absent so CI without SurrealDB still runs the rest of the suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.config import EngineConfig  # noqa: E402


def test_config_surreal_defaults_local():
    cfg = EngineConfig()
    assert cfg.store_backend in ("memory", "surrealdb")
    assert cfg.surreal_ns and cfg.surreal_db  # non-empty namespace/db
    assert cfg.surreal_dsn.startswith("ws://") or cfg.surreal_dsn.startswith("wss://")


def test_config_surreal_from_env(monkeypatch):
    monkeypatch.setenv("RAG_STORE_BACKEND", "surrealdb")
    monkeypatch.setenv("SURREAL_DSN", "wss://cloud.example/rpc")
    cfg = EngineConfig()
    assert cfg.store_backend == "surrealdb"
    assert cfg.surreal_dsn == "wss://cloud.example/rpc"


# ---- Task 2: schema DDL ------------------------------------------------
def test_schema_ddl_is_idempotent_shaped():
    from rag_engine.store.schema import ddl_statements
    stmts = ddl_statements()
    assert any("DEFINE TABLE" in s for s in stmts)
    assert any("HNSW" in s for s in stmts)       # vector index
    assert any("FULLTEXT" in s for s in stmts)   # full-text index
    # every DEFINE must be idempotent (OVERWRITE or IF NOT EXISTS) for safe re-apply
    for s in stmts:
        if s.strip().startswith("DEFINE"):
            assert "IF NOT EXISTS" in s or "OVERWRITE" in s, s


def test_schema_ddl_vector_dim_configurable():
    from rag_engine.store.schema import ddl_statements
    stmts = ddl_statements(vector_dim=384)
    assert any("DIMENSION 384" in s for s in stmts)


# ---- Task 3: SurrealStore (live, uses surreal_local fixture) ------------
def test_surreal_store_applies_ddl_and_roundtrips(surreal_local):
    from rag_engine.store.surreal import SurrealStore
    st = SurrealStore(dsn=surreal_local["dsn"], ns=surreal_local["ns"],
                      db=surreal_local["db"], user=surreal_local["user"],
                      password=surreal_local["pass"])
    st.connect()
    st.apply_schema()
    st.apply_schema()  # idempotent re-apply must not error (OVERWRITE)
    st.upsert_asset({"asset_id": "hr_records", "cls": "F", "level": 5,
                     "roles": ["C_SUITE"], "vertical": "PEOPLE",
                     "retrieval_mode": "vector"})
    got = st.get_asset("hr_records")
    assert got["cls"] == "F" and got["level"] == 5
    # upsert is idempotent (same id -> update, not duplicate)
    st.upsert_asset({"asset_id": "hr_records", "cls": "F", "level": 5,
                     "roles": ["C_SUITE"], "vertical": "PEOPLE",
                     "retrieval_mode": "vector"})
    assert st.count_assets() == 1
    st.close()


# ---- Task 4: estate -> SurrealDB target --------------------------------
def test_load_estate_into_surreal(surreal_local):
    from rag_engine.store.surreal import SurrealStore
    from seeds.targets.surreal_target import load_estate
    st = SurrealStore(dsn=surreal_local["dsn"], ns=surreal_local["ns"], db="estate",
                      user="root", password="root")
    st.connect()
    st.apply_schema()
    n = load_estate(st, scale=0.01)
    assert n == 25  # all catalog assets present
    pay = st.get_asset("payments_ledger")
    assert pay["cls"] == "D"
    assert pay["level"] == 4
    # columns carried through for masking policy
    assert any(c["name"] == "gov_id" and c["masked"] for c in pay["columns"])
    # idempotent reload (no duplicates)
    assert load_estate(st, scale=0.01) == 25
    assert st.count_assets() == 25
    st.close()

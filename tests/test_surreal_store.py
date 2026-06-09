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

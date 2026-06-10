"""P0.7 T2 — semantic-cache config knobs (CONFIGURABLE, schema-validated).

No magic numbers: similarity threshold / TTL / max-entries / backend / enabled are
all config, env-overridable, and validated at construction (invalid -> refuse to
start, never a silent default).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rag_engine.config import EngineConfig  # noqa: E402


def test_cache_defaults_present():
    cfg = EngineConfig()
    assert isinstance(cfg.cache_enabled, bool)
    assert 0.0 < cfg.cache_similarity_threshold <= 1.0
    assert cfg.cache_ttl_seconds > 0
    assert cfg.cache_max_entries > 0
    assert cfg.cache_backend in ("memory", "surreal")


def test_cache_config_from_env(monkeypatch):
    monkeypatch.setenv("RAG_CACHE_ENABLED", "0")
    monkeypatch.setenv("RAG_CACHE_SIMILARITY", "0.95")
    monkeypatch.setenv("RAG_CACHE_TTL_SECONDS", "120")
    monkeypatch.setenv("RAG_CACHE_MAX_ENTRIES", "256")
    monkeypatch.setenv("RAG_CACHE_BACKEND", "surreal")
    cfg = EngineConfig()
    assert cfg.cache_enabled is False
    assert cfg.cache_similarity_threshold == 0.95
    assert cfg.cache_ttl_seconds == 120
    assert cfg.cache_max_entries == 256
    assert cfg.cache_backend == "surreal"


def test_invalid_similarity_refuses_to_start(monkeypatch):
    monkeypatch.setenv("RAG_CACHE_SIMILARITY", "1.5")  # cosine can't exceed 1.0
    with pytest.raises(ValueError):
        EngineConfig()


def test_invalid_backend_refuses_to_start(monkeypatch):
    monkeypatch.setenv("RAG_CACHE_BACKEND", "redis-on-titan-pc")  # unsupported
    with pytest.raises(ValueError):
        EngineConfig()


def test_nonpositive_ttl_refuses_to_start(monkeypatch):
    monkeypatch.setenv("RAG_CACHE_TTL_SECONDS", "0")
    with pytest.raises(ValueError):
        EngineConfig()

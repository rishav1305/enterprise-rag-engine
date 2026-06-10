"""P0.8 T1 — self-RAG loop config (CONFIGURABLE, schema-validated).

Bounded iterations + thresholds + grader backend, all env-overridable and validated
at construction (invalid -> refuse to start).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rag_engine.config import EngineConfig  # noqa: E402


def test_selfrag_defaults_present():
    cfg = EngineConfig()
    assert isinstance(cfg.selfrag_enabled, bool)
    assert cfg.selfrag_max_iterations >= 1
    assert 0.0 < cfg.selfrag_relevance_threshold <= 1.0
    assert 0.0 < cfg.selfrag_groundedness_threshold <= 1.0
    assert cfg.selfrag_grader in ("fake", "openai")


def test_selfrag_from_env(monkeypatch):
    monkeypatch.setenv("RAG_SELFRAG_ENABLED", "0")
    monkeypatch.setenv("RAG_SELFRAG_MAX_ITERATIONS", "5")
    monkeypatch.setenv("RAG_SELFRAG_RELEVANCE", "0.4")
    monkeypatch.setenv("RAG_SELFRAG_GROUNDEDNESS", "0.7")
    monkeypatch.setenv("RAG_SELFRAG_GRADER", "openai")
    cfg = EngineConfig()
    assert cfg.selfrag_enabled is False
    assert cfg.selfrag_max_iterations == 5
    assert cfg.selfrag_relevance_threshold == 0.4
    assert cfg.selfrag_groundedness_threshold == 0.7
    assert cfg.selfrag_grader == "openai"


def test_zero_iterations_refuses_to_start(monkeypatch):
    monkeypatch.setenv("RAG_SELFRAG_MAX_ITERATIONS", "0")  # must be >= 1 (RESILIENT bound)
    with pytest.raises(ValueError):
        EngineConfig()


def test_invalid_relevance_refuses_to_start(monkeypatch):
    monkeypatch.setenv("RAG_SELFRAG_RELEVANCE", "1.5")
    with pytest.raises(ValueError):
        EngineConfig()


def test_invalid_grader_refuses_to_start(monkeypatch):
    monkeypatch.setenv("RAG_SELFRAG_GRADER", "magic-8-ball")
    with pytest.raises(ValueError):
        EngineConfig()

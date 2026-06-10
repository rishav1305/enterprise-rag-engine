"""P0.11b GATE B — rate-limit + per-day cap + synthetic-only refuse-to-start.

Tested with FAKE time + fake env (no live providers); enforced against live creds at
11c. These sit outside the leak oracle.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rag_engine.config import EngineConfig  # noqa: E402
from rag_engine.deploy.guards import (  # noqa: E402
    RateLimiter,
    RateLimitExceeded,
    assert_synthetic_only,
)


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


# ---- rate-limit + per-day cap ------------------------------------------
def test_per_minute_rate_limit_enforced():
    clk = _Clock()
    rl = RateLimiter(per_min=3, per_day=1000, now=clk)
    for _ in range(3):
        rl.check("user1")          # 3 allowed
    with pytest.raises(RateLimitExceeded):
        rl.check("user1")          # 4th in the same minute -> 429


def test_rate_limit_window_slides():
    clk = _Clock()
    rl = RateLimiter(per_min=2, per_day=1000, now=clk)
    rl.check("u")
    rl.check("u")
    with pytest.raises(RateLimitExceeded):
        rl.check("u")
    clk.advance(61)                # window passes
    rl.check("u")                  # allowed again


def test_per_day_cap_enforced():
    clk = _Clock()
    rl = RateLimiter(per_min=1000, per_day=5, now=clk)
    for i in range(5):
        clk.advance(1)
        rl.check("u")              # 5 allowed across the day
    with pytest.raises(RateLimitExceeded):
        rl.check("u")              # 6th -> daily cap


def test_keys_are_independent():
    rl = RateLimiter(per_min=1, per_day=1000, now=_Clock(), instance_per_min=1000)
    rl.check("a")
    rl.check("b")                  # a different key has its own budget


def test_instance_cap_blocks_key_rotation_bypass():
    # a client ROTATES the key per request to evade the per-key cap -> the INSTANCE-
    # WIDE cap must still trip. per-key high (10), instance cap low (3).
    rl = RateLimiter(per_min=10, per_day=10000, now=_Clock(), instance_per_min=3)
    rl.check("k0")
    rl.check("k1")
    rl.check("k2")                 # 3 distinct keys, each under its per-key cap
    with pytest.raises(RateLimitExceeded, match="instance"):
        rl.check("k3")            # 4th request (new key) -> instance cap trips


def test_instance_cap_window_slides():
    clk = _Clock()
    rl = RateLimiter(per_min=100, per_day=10000, now=clk, instance_per_min=2)
    rl.check("a")
    rl.check("b")
    with pytest.raises(RateLimitExceeded, match="instance"):
        rl.check("c")
    clk.advance(61)
    rl.check("d")                  # window passed -> allowed


# ---- synthetic-only refuse-to-start ------------------------------------
def test_synthetic_profile_passes_with_no_live_sources(monkeypatch):
    for e in ("GROQ_API_KEY", "RAG_SQL_LLM_API_KEY", "VOYAGE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(e, raising=False)
    cfg = EngineConfig()           # defaults: memory store, fake gen
    assert cfg.demo_profile == "synthetic"
    assert_synthetic_only(cfg)     # no raise


def test_synthetic_profile_refuses_live_llm_credential(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk-live-key")
    cfg = EngineConfig()
    with pytest.raises(RuntimeError, match="SYNTHETIC-ONLY"):
        assert_synthetic_only(cfg)


def test_synthetic_profile_refuses_live_surreal_cloud(monkeypatch):
    for e in ("GROQ_API_KEY", "RAG_SQL_LLM_API_KEY", "VOYAGE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(e, raising=False)
    monkeypatch.setenv("RAG_STORE_BACKEND", "surrealdb")
    monkeypatch.setenv("SURREAL_DSN", "wss://cloud.surrealdb.com/rpc")
    cfg = EngineConfig()
    with pytest.raises(RuntimeError, match="SYNTHETIC-ONLY"):
        assert_synthetic_only(cfg)


def test_production_profile_is_exempt(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk-live")
    monkeypatch.setenv("RAG_DEMO_PROFILE", "production")
    cfg = EngineConfig()
    assert_synthetic_only(cfg)     # production opted in -> no raise


def test_config_gate_b_knobs_validated(monkeypatch):
    monkeypatch.setenv("RAG_RATE_LIMIT_PER_MIN", "0")
    with pytest.raises(ValueError):
        EngineConfig()

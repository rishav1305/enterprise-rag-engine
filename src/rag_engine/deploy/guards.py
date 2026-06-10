"""Rate-limit + per-day cap + synthetic-only guard (P0.11b GATE B).

``RateLimiter`` enforces a per-key requests/min sliding window AND a per-key per-day
cap, BEFORE any LLM/embedding call. ``assert_synthetic_only`` refuses to start the
demo if a non-synthetic data source (live SurrealDB Cloud / live LLM / live embedder)
is configured under the ``synthetic`` demo profile.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque


class RateLimitExceeded(Exception):
    """Raised (and mapped to HTTP 429) when a key exceeds its rate or daily cap."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class RateLimiter:
    """Per-key sliding-window rate limit + per-day cap. In-process (single instance);
    for multi-instance, back it with Redis — same interface.

    ``check(key)`` raises RateLimitExceeded if the key is over either bound; otherwise
    it records the request. Time is injectable for deterministic tests.
    """

    def __init__(self, per_min: int, per_day: int, now=time.monotonic,
                 instance_per_min: int | None = None) -> None:
        if per_min < 1 or per_day < 1:
            raise ValueError("per_min and per_day must be >= 1")
        self.per_min = per_min
        self.per_day = per_day
        # INSTANCE-WIDE cap (total req/min across ALL keys) — a client that rotates
        # X-User-Id per request bypasses the per-key cap; the instance cap closes that.
        # Defaults to a generous multiple of the per-key cap.
        self.instance_per_min = instance_per_min if instance_per_min is not None \
            else per_min * 50
        self._now = now
        self._window: dict[str, deque[float]] = defaultdict(deque)   # last-60s timestamps
        self._day_count: dict[str, int] = defaultdict(int)
        self._day_start: dict[str, float] = {}
        self._instance_window: deque[float] = deque()   # ALL keys, last-60s

    def check(self, key: str) -> None:
        t = self._now()
        # INSTANCE-WIDE per-minute cap FIRST (key-rotation can't bypass it).
        iw = self._instance_window
        while iw and (t - iw[0]) >= 60:
            iw.popleft()
        if len(iw) >= self.instance_per_min:
            raise RateLimitExceeded(
                f"instance rate limit ({self.instance_per_min}/min) exceeded")
        # per-day cap (rolling 24h window per key)
        start = self._day_start.get(key)
        if start is None or (t - start) >= 86400:
            self._day_start[key] = t
            self._day_count[key] = 0
        if self._day_count[key] >= self.per_day:
            raise RateLimitExceeded(f"daily query cap ({self.per_day}) exceeded")
        # per-minute sliding window (per key)
        w = self._window[key]
        while w and (t - w[0]) >= 60:
            w.popleft()
        if len(w) >= self.per_min:
            raise RateLimitExceeded(f"rate limit ({self.per_min}/min) exceeded")
        # record (both windows)
        w.append(t)
        self._day_count[key] += 1
        iw.append(t)


def assert_synthetic_only(config) -> None:
    """Refuse to start if a non-synthetic data source is reachable under the
    'synthetic' demo profile. A leak in synthetic data is theater; against real data
    it is not — so the demo MUST NOT be able to reach a real private source.

    Synthetic-profile rules: the store must be in-memory (no live SurrealDB Cloud DSN
    pointing off-box), and NO live LLM/embedding/DB credential may be present in the
    environment (those would route to real providers / data). 'production' profile is
    exempt (operator opted in).
    """
    if config.demo_profile != "synthetic":
        return  # production profile: operator has opted into real sources.

    violations: list[str] = []
    # a live SurrealDB Cloud DSN (wss:// off-box) is a non-synthetic source.
    if config.store_backend == "surrealdb":
        dsn = config.surreal_dsn
        if dsn.startswith("wss://") and "127.0.0.1" not in dsn and "localhost" not in dsn:
            violations.append(f"live SurrealDB Cloud DSN configured ({dsn})")
    # live provider creds would route to real models/data.
    for env in ("GROQ_API_KEY", "RAG_SQL_LLM_API_KEY", "VOYAGE_API_KEY",
                "ANTHROPIC_API_KEY"):
        if os.getenv(env):
            violations.append(f"live provider credential {env} is set")
    # explicit live-source opt-ins
    if config.selfrag_grader == "openai":
        violations.append("selfrag_grader=openai (live LLM grader)")
    if config.sql_generator in ("groq", "nvidia"):
        violations.append(f"sql_generator={config.sql_generator} (live LLM)")

    if violations:
        raise RuntimeError(
            "SYNTHETIC-ONLY VIOLATION (demo_profile=synthetic refuses to start): "
            + "; ".join(violations)
            + ". A demo leak must be in synthetic data only — set RAG_DEMO_PROFILE="
              "production to opt into real sources (NOT for the public demo)."
        )


__all__ = ["RateLimiter", "RateLimitExceeded", "assert_synthetic_only"]

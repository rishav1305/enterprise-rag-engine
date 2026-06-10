"""Deploy-security primitives (P0.11b GATE B) — abuse caps + synthetic-only guard.

These sit OUTSIDE the leak oracle (the review net can't catch them): a public demo
URL backed by live keys needs a rate-limit + per-day cap (so anyone can't run up
real bills), and a refuse-to-start assertion that only synthetic data is reachable
(a leak in synthetic data is theater; against real data it is not).
"""

from .guards import (
    RateLimiter,
    RateLimitExceeded,
    assert_synthetic_only,
)

__all__ = ["RateLimiter", "RateLimitExceeded", "assert_synthetic_only"]

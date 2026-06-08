"""Meridian Data Foundation (P0.1a).

Deterministic, seeded, coherent synthetic data + query-in-place fixtures for
the real public sources, generated against the world bible
(``docs/meridian-org-and-data.md``). Every downstream CLEARANCE phase consumes
this estate: catalog (P0.1b), poly-store (P0.2a), TurboVec index (P0.2b),
text-to-SQL (P0.3), glossary (P0.4), the leak-audit oracle, and the funnel.

The estate is reproducible byte-for-byte under a fixed ``SEED`` so the
adversarial leak audit is deterministic.
"""

from __future__ import annotations

SEED = 1337  # single source of determinism for the whole estate

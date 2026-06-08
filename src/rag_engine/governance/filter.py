"""The permission-aware post-filter.

This is the chokepoint. At the precise moment retrieval returns the top-K
chunks, the filter cross-references each chunk's ACLs against the active
session.

Governance-v2 (P0.1b) admits more than just ``allow``:
  * ``allow``   — passes through unchanged.
  * ``mask``    — admitted; PII/secured columns are redacted downstream (the row
                  still reaches the model, masked — least-privilege, not blackout).
  * ``partial`` — admitted with a row-scope predicate on the decision.
  * ``deny``    — **dropped before the model can ever see it** (the original
                  invariant). Denied chunks never touch generation, so the model
                  physically cannot leak them.

The audit trail records the per-chunk decision (incl. ``mask_reason``/``scope``)
regardless of admission, so every drop and redaction is explainable (TRANSPARENT).
"""

from __future__ import annotations

from ..schemas import GovernanceDecision, ScoredChunk, Session
from . import access


class SecurityFilter:
    def apply(
        self, candidates: list[ScoredChunk], session: Session
    ) -> tuple[list[ScoredChunk], list[GovernanceDecision]]:
        admitted: list[ScoredChunk] = []
        trail: list[GovernanceDecision] = []
        for sc in candidates:
            decision = access.evaluate(sc.chunk, session)
            trail.append(decision)
            # Only DENY is dropped-before-model; allow/mask/partial flow through
            # (mask/partial carry their redaction/scope on the decision record).
            if decision.decision != "deny":
                admitted.append(sc)
        return admitted, trail

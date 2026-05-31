"""The permission-aware post-filter.

This is the chokepoint. At the precise moment retrieval returns the top-K
chunks, the filter cross-references each chunk's ACLs against the active
session and **drops any chunk the caller is not cleared for before it can
enter the LLM context window**. The dropped chunks never touch generation, so
the model physically cannot leak them.
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
            if decision.decision == "allow":
                admitted.append(sc)
        return admitted, trail

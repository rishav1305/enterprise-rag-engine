"""Access decisioning — the single source of truth for 'can this session read this chunk?'.

The rule is deliberately strict and easy to audit:
  1. A public chunk (clearance 0 and no restricting roles) is always allowed.
  2. Otherwise the session's clearance must be >= the chunk's clearance level,
     AND the session must hold at least one of the chunk's allowed roles.
Both conditions must hold. Fail-closed: anything ambiguous is denied.
"""

from __future__ import annotations

from ..schemas import EnrichedChunk, GovernanceDecision, Session


def evaluate(chunk: EnrichedChunk, session: Session) -> GovernanceDecision:
    sec = chunk.security
    base = dict(
        chunk_id=chunk.chunk_id,
        parent_doc_id=chunk.parent_doc_id,
        required_roles=list(sec.allowed_roles),
        session_roles=list(session.roles),
    )

    if sec.is_public:
        return GovernanceDecision(decision="allow", reason="public_content", **base)

    if session.clearance_level < sec.clearance_level:
        return GovernanceDecision(
            decision="deny",
            reason=(
                f"insufficient_clearance "
                f"(session L{session.clearance_level} < required L{sec.clearance_level})"
            ),
            **base,
        )

    session_roles = set(session.roles)
    if session_roles.isdisjoint(sec.allowed_roles):
        return GovernanceDecision(
            decision="deny",
            reason=f"role_mismatch (need one of {sec.allowed_roles})",
            **base,
        )

    return GovernanceDecision(
        decision="allow",
        reason="clearance_and_role_satisfied",
        **base,
    )

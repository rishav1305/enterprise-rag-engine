"""Access decisioning — the single source of truth for 'can this session read this?'.

Governance-v2 (P0.1b) extends the original binary allow/deny to four decisions:

  * ``allow``   — full access.
  * ``mask``    — admitted but PII/secured columns are redacted (customer-PII class D
                  for L2-L3; raw only at L4+). The row still reaches the model masked.
  * ``partial`` — row-scoped access (e.g. Engineer sees own-component security tickets).
  * ``deny``    — dropped before the model + audited.

The rule stays strict, auditable, and fail-closed. It is BACKWARD COMPATIBLE:
chunks with no ``sensitivity_class`` fall through to the original level +
allowed_roles gate, so the existing INTERN-vs-CFO leak demo behaves identically.
"""

from __future__ import annotations

from ..schemas import EnrichedChunk, GovernanceDecision, Session

# class D (customer PII): mask for L2-L3, raw at L4+, deny below L2.
_PII_CLASS = "D"


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

    cls = sec.sensitivity_class
    level = session.clearance_level
    roles = set(session.roles)

    # --- masking leg: customer PII (class D) -----------------------------
    if cls == _PII_CLASS:
        if level >= 4:
            return GovernanceDecision(decision="allow", reason="pii_cleared", **base)
        if level >= 2:
            return GovernanceDecision(
                decision="mask", reason="pii_masked", mask_reason="pii_mask", **base
            )
        return GovernanceDecision(decision="deny", reason="pii_below_min_level", **base)

    # --- level gate ------------------------------------------------------
    if level < sec.clearance_level:
        return GovernanceDecision(
            decision="deny",
            reason=(
                f"insufficient_clearance "
                f"(session L{level} < required L{sec.clearance_level})"
            ),
            **base,
        )

    # --- need-to-know gate (non-monotonic) -------------------------------
    ntk = set(sec.need_to_know_roles)
    if ntk and roles.isdisjoint(ntk):
        # PRECEDENCE: this branch is reached only when the session has NO full
        # need-to-know role, so a dual-role holder (full + partial) skips it and
        # falls through to ALLOW below. Full access always wins over partial.
        partial_for = (
            set(chunk.metadata.get("partial_for", [])) if chunk.metadata else set()
        )
        if partial_for and roles & partial_for:
            return GovernanceDecision(
                decision="partial", reason="scoped_access", scope="own_component", **base
            )
        return GovernanceDecision(
            decision="deny",
            reason=f"need_to_know (need one of {sorted(ntk)})",
            **base,
        )

    # --- allowed_roles gate (legacy path; preserved for un-classed chunks)
    # NB: matches original semantics — a non-public chunk with empty allowed_roles
    # is disjoint with the session and therefore denied (fail-closed).
    if roles.isdisjoint(sec.allowed_roles):
        return GovernanceDecision(
            decision="deny",
            reason=f"role_mismatch (need one of {sec.allowed_roles})",
            **base,
        )

    return GovernanceDecision(
        decision="allow", reason="clearance_and_role_satisfied", **base
    )

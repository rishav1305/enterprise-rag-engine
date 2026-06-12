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

# The canonical Meridian sensitivity classes (A-N). Kept local (no `seeds` import —
# that pulls heavy seed-gen deps at runtime). The empty string "" means un-classed
# (the legacy level+allowed_roles path). ANY OTHER non-empty value is unrecognized
# and DENIED (fail-closed) — a malformed/typo class must never bypass the gates.
_VALID_CLASSES = frozenset("ABCDEFGHIJKLMN")


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

    # --- fail-closed on an UNRECOGNIZED class (defense in depth) ----------
    # The ingestion loader normalizes + rejects bad classes, but anything that reaches
    # evaluate with a non-empty class that isn't a known A-N class (a typo, a catalog
    # asset, a seed that skipped the loader) must DENY — never fall through to the
    # legacy role gate (which is guarded by `not cls`) and out to ALLOW.
    if cls and cls not in _VALID_CLASSES:
        return GovernanceDecision(
            decision="deny", reason=f"unrecognized_sensitivity_class ({cls!r})", **base
        )

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

    # --- allowed_roles gate (LEGACY path — un-classed chunks only) -------
    # Classed chunks are governed by the level + need-to-know gates above; a
    # classed chunk that reaches here (level OK, need-to-know satisfied or absent)
    # is allowed — a level-only class (empty need-to-know, e.g. B/C/J/L) must NOT
    # be denied for lacking a role (that was the _CLASS_ROLES drift bug). For
    # un-classed legacy chunks we keep the original fail-closed role gate: a
    # non-public chunk with empty allowed_roles is disjoint and therefore denied.
    if not cls and roles.isdisjoint(sec.allowed_roles):
        return GovernanceDecision(
            decision="deny",
            reason=f"role_mismatch (need one of {sec.allowed_roles})",
            **base,
        )

    return GovernanceDecision(
        decision="allow", reason="clearance_and_role_satisfied", **base
    )

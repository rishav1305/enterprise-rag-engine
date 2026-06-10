"""LocalReBAC — a zero-dep relationship-tuple kernel (the SpiceDB *model*).

This proves the ReBAC APPROACH (relationship tuples + a sub-linear list-objects
lookup) without requiring the SpiceDB binary or Oso Cloud creds, so the parity
guarantee is provable in plain CI. The real SpiceDB / Oso backends (gated) encode
the same tuples in their own schemas and are parity-checked against this + the
in-process reference.

Model (relationship tuples written per chunk, mirroring the access.evaluate rules):
    chunk:<id> public               -> true|false
    chunk:<id> class                -> A..L
    chunk:<id> min_level            -> int (required clearance)
    chunk:<id> ntk_role             -> role        (0..n need-to-know roles)
    chunk:<id> partial_role         -> role        (0..n scoped-access roles)
    chunk:<id> allowed_role         -> role        (0..n legacy allowed_roles; the
                                                    un-classed role gate, access.py:87)

A session is {roles, clearance_level}. ``authorized_ids`` returns the chunks whose
governance decision is NOT deny — computed from the tuples, NOT by calling
access.evaluate (so the parity test is meaningful: an independent derivation that
must agree). The lookup is sub-linear at scale: tuples are indexed by chunk and
only candidate chunks are probed (no full-corpus rescore of governance per query).

PARITY INVARIANT: for any session + candidate set this returns EXACTLY the ids
InProcessAllowlist returns. Verified in tests/test_rebac_parity.py. Any divergence
is a security defect.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ...schemas import EnrichedChunk, Session

_PII_CLASS = "D"


@dataclass(frozen=True, slots=True)
class ReBACTuple:
    """One relationship fact: (resource, relation, value)."""

    resource: str   # "chunk:<id>"
    relation: str   # public|class|min_level|ntk_role|partial_role|allowed_role
    value: str


def governance_tuples(chunk: EnrichedChunk) -> list[ReBACTuple]:
    """Emit the ReBAC relationship tuples for one chunk (the sync surface).

    These tuples are exactly the facts access.evaluate consumes — written into the
    ReBAC store so the engine can derive the decision independently.
    """
    rid = f"chunk:{chunk.chunk_id}"
    sec = chunk.security
    tuples = [
        ReBACTuple(rid, "public", "true" if sec.is_public else "false"),
        ReBACTuple(rid, "class", sec.sensitivity_class or ""),
        ReBACTuple(rid, "min_level", str(sec.clearance_level)),
    ]
    for r in sec.need_to_know_roles:
        tuples.append(ReBACTuple(rid, "ntk_role", r))
    partial_for = (chunk.metadata or {}).get("partial_for", []) if chunk.metadata else []
    for r in partial_for:
        tuples.append(ReBACTuple(rid, "partial_role", r))
    # Legacy allowed_roles — the role gate access.py:87 applies to UN-CLASSED
    # non-public chunks. Emitted always (cheap); the decision only consults them on
    # the un-classed leg, mirroring access.py exactly.
    for r in sec.allowed_roles:
        tuples.append(ReBACTuple(rid, "allowed_role", r))
    return tuples


def _decision_is_retrievable(facts: dict, session: Session) -> bool:
    """Derive 'session may retrieve this chunk' (decision != deny) from tuples.

    Mirrors access.evaluate's deny conditions exactly — but reads the relationship
    facts, not the chunk object. Kept rule-for-rule aligned with access.py.
    """
    if facts.get("public") == "true":
        return True

    cls = facts.get("class") or ""
    level = session.clearance_level
    roles = set(session.roles)

    # masking leg: class D (customer PII) — deny only below L2.
    if cls == _PII_CLASS:
        return level >= 2  # L2-L3 mask (retrievable), L4+ allow; <L2 deny.

    # level gate
    min_level = int(facts.get("min_level", "0") or "0")
    if level < min_level:
        return False

    # need-to-know (non-monotonic): denied unless the session holds an NTK role OR
    # a partial-scope role.
    ntk = facts.get("ntk_role", set())
    if ntk and roles.isdisjoint(ntk):
        partial = facts.get("partial_role", set())
        if partial and roles & partial:
            return True  # partial (scoped) access -> retrievable
        return False

    # legacy allowed_roles gate — mirrors access.py:87 EXACTLY: for an UN-CLASSED
    # (sensitivity_class == "") non-public chunk, deny when the session's roles are
    # disjoint from the chunk's allowed_roles. Classed chunks are fully decided by
    # the level + need-to-know gates above and must NOT be role-gated here (that was
    # the original _CLASS_ROLES drift bug). This closes the LocalReBAC divergence:
    # previously this returned True unconditionally, leaking role-gated legacy chunks.
    if not cls:
        allowed = facts.get("allowed_role", set())
        if roles.isdisjoint(allowed):
            return False

    return True


class LocalReBACAllowlist:
    """In-process ReBAC engine: sync tuples, then list-objects per session.

    ``authorized_ids`` is the AllowlistBackend contract. Internally it indexes the
    synced tuples by chunk id so a lookup touches only the candidate chunks
    (sub-linear in the corpus), the ELASTIC win over the O(N) governance rescan.
    """

    def __init__(self) -> None:
        # chunk_id -> {relation: value | set(values)}
        self._facts: dict[str, dict] = {}

    def sync(self, chunks: Iterable[EnrichedChunk]) -> None:
        for chunk in chunks:
            facts: dict = {}
            for t in governance_tuples(chunk):
                if t.relation in ("ntk_role", "partial_role", "allowed_role"):
                    facts.setdefault(t.relation, set()).add(t.value)
                else:
                    facts[t.relation] = t.value
            self._facts[chunk.chunk_id] = facts

    def authorized_ids(
        self, session: Session, candidates: Iterable[EnrichedChunk]
    ) -> list[str]:
        # Auto-sync any candidate not yet in the store (so the backend is
        # drop-in: callers don't have to pre-sync). Order-preserving.
        out: list[str] = []
        for chunk in candidates:
            if chunk.chunk_id not in self._facts:
                self.sync([chunk])
            if _decision_is_retrievable(self._facts[chunk.chunk_id], session):
                out.append(chunk.chunk_id)
        return out

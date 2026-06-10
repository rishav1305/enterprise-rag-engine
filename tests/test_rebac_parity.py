"""WORKER-D — ReBAC backend PARITY with InProcessAllowlist (the leak/over-deny guard).

The optimization must NOT change the decision: every ReBAC backend MUST return
EXACTLY the allow/deny set InProcessAllowlist returns, for every (session ×
candidate) cell. A superset is a LEAK; a subset is an OVER-DENY. This is the
210-cell-style parity gate for the allowlist engine.

- LocalReBAC runs ALWAYS (zero-dep) -> parity provable in plain CI.
- SpiceDB / Oso run when their binary/creds are present (@pytest.mark.spicedb /
  @pytest.mark.oso), so parity is enforced on the real engines on demand.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from rag_engine.governance.allowlist import InProcessAllowlist  # noqa: E402
from rag_engine.governance.rebac import LocalReBACAllowlist  # noqa: E402
from rag_engine.schemas import EnrichedChunk, SecurityContext, Session  # noqa: E402


def _chunk(cid, cls, level, ntk=None, public=False, partial_for=None,
           allowed_roles=None):
    meta = {"partial_for": partial_for} if partial_for else {}
    # is_public is DERIVED (clearance_level==0 AND PUBLIC/no roles); model a public
    # chunk that way rather than via a (nonexistent) flag.
    if public:
        sec = SecurityContext(allowed_roles=["PUBLIC"], clearance_level=0,
                              sensitivity_class=cls, need_to_know_roles=[])
    else:
        # allowed_roles defaults to ntk for the classed legs; the un-classed LEGACY
        # leg sets allowed_roles INDEPENDENTLY (ntk empty) so access.py:87's
        # role-gate fires.
        sec = SecurityContext(
            allowed_roles=allowed_roles if allowed_roles is not None else (ntk or []),
            clearance_level=level, sensitivity_class=cls,
            need_to_know_roles=ntk or [],
        )
    return EnrichedChunk(
        chunk_id=cid, parent_doc_id=cid, parent_title="t", content="x",
        security=sec, metadata=meta,
    )


def _candidate_matrix():
    """A spread spanning every governance leg: public, PII-mask, level-gate,
    need-to-know, partial-scope, exec-comp deny, AND the un-classed LEGACY role gate
    (access.py:87) — the leg the divergence lived in."""
    return [
        _chunk("pub", "A", 1, public=True),            # public -> always allow
        _chunk("internal", "C", 2),                    # level gate L2
        _chunk("secret", "E", 4),                      # level gate L4
        _chunk("pii", "D", 1),                         # PII: mask L2-3 / deny <L2 / allow L4+
        _chunk("comp", "F", 5, ntk=["C_SUITE"]),       # NTK + level 5
        _chunk("ticket", "G", 3, ntk=["ENGINEERING"],  # NTK with partial-scope path
                partial_for=["ON_CALL"]),
        # ---- un-classed LEGACY role gate (sensitivity_class == "") ----------
        # access.py:87 DENIES when session roles are disjoint from allowed_roles.
        _chunk("legacy_fin", "", 1, allowed_roles=["FINANCE"]),   # role-gated: FINANCE only
        _chunk("legacy_eng", "", 1, allowed_roles=["ENGINEERING"]),  # match-role variant
        # un-classed, level-0 but NOT public (has a non-PUBLIC required role) — must
        # NOT be treated as public; role gate still applies.
        _chunk("legacy_l0", "", 0, allowed_roles=["HR_ADMIN"]),
    ]


def _session_matrix():
    return [
        Session(user_id="intern", roles=["INTERN"], clearance_level=1),
        Session(user_id="analyst", roles=["EMPLOYEE"], clearance_level=2),
        Session(user_id="mgr", roles=["MANAGER", "ENGINEERING"], clearance_level=3),
        Session(user_id="oncall", roles=["ON_CALL"], clearance_level=2),
        # oncall_sr exercises the partial-scope POSITIVE path: ON_CALL + L>=3 so the
        # 'ticket' chunk grants scoped (partial) access -> retrievable. Without this
        # cell, a never-grant-scoped mutation passes parity silently (over-deny hole).
        Session(user_id="oncall_sr", roles=["ON_CALL"], clearance_level=3),
        Session(user_id="dir", roles=["DIRECTOR"], clearance_level=4),
        Session(user_id="cfo", roles=["C_SUITE", "FINANCE"], clearance_level=5),
        Session(user_id="nobody", roles=[], clearance_level=0),
    ]


def _assert_parity(backend, label):
    reference = InProcessAllowlist()
    chunks = _candidate_matrix()
    mismatches = []
    for s in _session_matrix():
        ref = reference.authorized_ids(s, chunks)
        got = backend.authorized_ids(s, chunks)
        if set(ref) != set(got):
            leaked = set(got) - set(ref)        # over-permit -> LEAK
            overdenied = set(ref) - set(got)    # over-deny
            mismatches.append(
                f"{s.user_id}: leak={sorted(leaked)} over_deny={sorted(overdenied)}"
            )
    assert not mismatches, f"{label} diverged from InProcessAllowlist:\n" + "\n".join(mismatches)


def test_local_rebac_parity_with_inprocess():
    """ALWAYS runs — the zero-dep ReBAC kernel must match the reference exactly."""
    _assert_parity(LocalReBACAllowlist(), "LocalReBAC")


@pytest.mark.spicedb
def test_spicedb_parity_with_inprocess():  # pragma: no cover - gated
    if not os.getenv("SPICEDB_ENDPOINT"):
        pytest.skip("SpiceDB endpoint not available (set SPICEDB_ENDPOINT/SPICEDB_TOKEN)")
    from rag_engine.governance.rebac.spicedb import SpiceDBAllowlist
    backend = SpiceDBAllowlist(os.environ["SPICEDB_ENDPOINT"], os.environ["SPICEDB_TOKEN"])
    backend.sync(_candidate_matrix())
    _assert_parity(backend, "SpiceDB")


@pytest.mark.oso
def test_oso_parity_with_inprocess():  # pragma: no cover - gated
    if not os.getenv("OSO_AUTH"):
        pytest.skip("Oso Cloud API key not available (set OSO_AUTH)")
    from rag_engine.governance.rebac.oso import OsoCloudAllowlist
    backend = OsoCloudAllowlist(os.getenv("OSO_URL", "https://cloud.osohq.com"),
                                os.environ["OSO_AUTH"])
    backend.sync(_candidate_matrix())
    _assert_parity(backend, "Oso")

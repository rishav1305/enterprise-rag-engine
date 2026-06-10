"""P0.7 T0 — AuthScope + scope fingerprint (the permission boundary in the key).

The cache key MUST separate sessions by their governance-relevant identity
(clearance_level + the set of roles), so an entry populated under one authorization
scope can never be looked up under a different one. need-to-know is per-chunk
(matched against session.roles), so the session's roles + clearance ARE the scope.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.cache.key import AuthScope  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402


def test_scope_from_session_carries_clearance_and_roles():
    s = Session(user_id="a", roles=["FINANCE", "MANAGER"], clearance_level=3)
    scope = AuthScope.from_session(s)
    assert scope.clearance_level == 3
    assert set(scope.roles) == {"FINANCE", "MANAGER"}


def test_fingerprint_is_role_order_independent():
    # roles are a SET — order must not change the fingerprint (else cache misses
    # spuriously and, worse, two orderings of the same scope key differently).
    a = AuthScope.from_session(Session(user_id="a", roles=["FINANCE", "MANAGER"], clearance_level=3))
    b = AuthScope.from_session(Session(user_id="b", roles=["MANAGER", "FINANCE"], clearance_level=3))
    assert a.fingerprint() == b.fingerprint()


def test_fingerprint_separates_clearance():
    lo = AuthScope.from_session(Session(user_id="a", roles=["EMPLOYEE"], clearance_level=1))
    hi = AuthScope.from_session(Session(user_id="b", roles=["EMPLOYEE"], clearance_level=5))
    assert lo.fingerprint() != hi.fingerprint()   # different clearance -> different scope


def test_fingerprint_separates_roles():
    eng = AuthScope.from_session(Session(user_id="a", roles=["ENGINEERING"], clearance_level=3))
    fin = AuthScope.from_session(Session(user_id="b", roles=["FINANCE"], clearance_level=3))
    assert eng.fingerprint() != fin.fingerprint()  # different roles -> different scope


def test_fingerprint_is_stable_hex():
    s = Session(user_id="a", roles=["FINANCE"], clearance_level=3)
    fp1 = AuthScope.from_session(s).fingerprint()
    fp2 = AuthScope.from_session(s).fingerprint()
    assert fp1 == fp2 and isinstance(fp1, str) and len(fp1) == 64  # sha256 hex


def test_scope_is_hashable_and_frozen():
    scope = AuthScope.from_session(Session(user_id="a", roles=["FINANCE"], clearance_level=3))
    {scope: 1}  # hashable -> usable as a dict/index key


def test_control_char_role_is_rejected():
    # the fingerprint joins roles with \x1f; a role literally containing a control
    # char could alias two scopes -> the Session validator must refuse it.
    import pytest
    with pytest.raises(ValueError):
        Session(user_id="a", roles=["FIN\x1fANCE"], clearance_level=3)


def test_control_char_aliasing_is_blocked_endtoend():
    # ['A\x1fB'] must NOT be allowed (which would fingerprint-collide with ['A','B']).
    import pytest
    with pytest.raises(ValueError):
        Session(user_id="a", roles=["A\x1fB"], clearance_level=3)
    # the legitimate two-role scope is fine and distinct
    two = AuthScope.from_session(Session(user_id="b", roles=["A", "B"], clearance_level=3))
    assert isinstance(two.fingerprint(), str)

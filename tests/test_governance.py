"""Unit tests for the access decision logic — fail-closed behaviour."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.governance import access
from rag_engine.schemas import EnrichedChunk, SecurityContext, Session


def _chunk(roles, level):
    return EnrichedChunk(
        chunk_id="d::0", parent_doc_id="d", parent_title="Doc", content="x",
        security=SecurityContext(allowed_roles=roles, clearance_level=level),
    )


def test_public_always_allowed():
    d = access.evaluate(_chunk(["PUBLIC"], 0), Session(user_id="u", roles=[], clearance_level=0))
    assert d.decision == "allow"


def test_low_clearance_denied():
    d = access.evaluate(
        _chunk(["C_SUITE"], 4), Session(user_id="u", roles=["C_SUITE"], clearance_level=1)
    )
    assert d.decision == "deny" and "clearance" in d.reason


def test_role_mismatch_denied():
    d = access.evaluate(
        _chunk(["C_SUITE"], 4), Session(user_id="u", roles=["INTERN"], clearance_level=5)
    )
    assert d.decision == "deny" and "role" in d.reason


def test_authorised_allowed():
    d = access.evaluate(
        _chunk(["C_SUITE", "FINANCE"], 4),
        Session(user_id="u", roles=["FINANCE"], clearance_level=5),
    )
    assert d.decision == "allow"

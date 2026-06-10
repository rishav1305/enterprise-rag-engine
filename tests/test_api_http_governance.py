"""P0.11b B1 — GATE A: the /query HTTP entry point governs end-to-end (TestClient).

The demo persona switcher calls POST /query with different X-Clearance/X-User-Roles
headers. These tests hit the ACTUAL HTTP path (FastAPI TestClient) — including the
header->Session derivation in api.py — NOT pipeline.query() directly. They prove:
  1. an under-cleared persona cannot retrieve restricted content through /query;
  2. SELF-ESCALATION is impossible — a role/clearance in the request BODY is IGNORED
     (the Session is derived server-side from HEADERS only), and a forged header
     can't grant content the persona's real entitlement wouldn't (the headers ARE the
     entitlement in this demo, so we assert the body can't override them).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# leak signals from the class-F restricted exec-comp doc that ACTUALLY appear in a
# cleared session's answer/citations (verified: a C_SUITE answer contains the title
# text + the hr-exec-comp-2026 citation; an intern's does not). The dollar figure
# alone isn't surfaced by the extractive generator, so we key on what really leaks.
RESTRICTED_TEXT = "Executive Compensation Schedule 2026"
RESTRICTED_DOC = "hr-exec-comp-2026"


def _restricted_leaked(resp_json: dict) -> bool:
    """True if the restricted doc's content OR citation appears in the response."""
    if RESTRICTED_TEXT in (resp_json.get("answer") or ""):
        return True
    cited = {c.get("parent_doc_id") for c in resp_json.get("citations", [])}
    return RESTRICTED_DOC in cited


@pytest.fixture(scope="module")
def client():
    from rag_engine.api import app
    with TestClient(app) as c:
        yield c


def _ask(client, question, *, roles="PUBLIC", clearance=0, body_extra=None):
    body = {"question": question}
    if body_extra:
        body.update(body_extra)
    return client.post("/query", json=body, headers={
        "X-User-Id": "tester", "X-User-Roles": roles, "X-Clearance": str(clearance),
    })


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_intern_cannot_retrieve_restricted_over_http(client):
    # an L1 INTERN asks about exec compensation -> the restricted figure must NOT be
    # in the HTTP response (the same governance as pipeline.query, over the wire).
    r = _ask(client, "what is the executive compensation schedule",
             roles="INTERN", clearance=1)
    assert r.status_code == 200
    assert not _restricted_leaked(r.json()), \
        "HTTP LEAK: intern retrieved restricted comp over /query"


def test_cleared_session_can_retrieve(client):
    # a C_SUITE/L5 session legitimately retrieves it (governance is real, not a blanket
    # block). The answer references the schedule.
    r = _ask(client, "what is the executive compensation schedule",
             roles="C_SUITE", clearance=5)
    assert r.status_code == 200
    assert _restricted_leaked(r.json()), \
        "cleared C_SUITE should retrieve the restricted doc (proves the leak signal is real)"


def test_body_role_is_ignored_no_self_escalation(client):
    # SELF-ESCALATION attempt: an INTERN passes a privileged role/clearance in the BODY.
    # The server derives the Session from HEADERS only, so the body is IGNORED -> the
    # intern stays L1 and CANNOT retrieve the restricted figure.
    r = _ask(client, "what is the executive compensation schedule",
             roles="INTERN", clearance=1,
             body_extra={"roles": ["C_SUITE"], "clearance_level": 5,
                         "session": {"roles": ["C_SUITE"], "clearance_level": 5}})
    assert r.status_code == 200
    assert not _restricted_leaked(r.json()), \
        "SELF-ESCALATION: a body role/clearance overrode the header-derived Session"


def test_unknown_body_fields_rejected_or_ignored(client):
    # the QueryRequest schema only accepts `question`; extra fields must not become
    # part of governance. (pydantic ignores/forbids extras -> still governed.)
    r = _ask(client, "remote work policy", roles="INTERN", clearance=1,
             body_extra={"admin": True, "bypass_governance": True})
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        assert not _restricted_leaked(r.json())

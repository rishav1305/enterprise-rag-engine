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

import json  # noqa: E402

# leak signals from the class-F restricted exec-comp doc. The detector scans the
# ENTIRE serialized response — so it catches the METADATA-DISCLOSURE class too: a
# denied caller must learn NOTHING about restricted content — not its body, not its
# doc id, not the roles/clearance that would unlock it (the trail-disclosure bug).
RESTRICTED_TEXT = "Executive Compensation Schedule 2026"
RESTRICTED_DOC = "hr-exec-comp-2026"
ACL_MARKERS = ("hr-exec-comp-2026", "C_SUITE", "HR_ADMIN", "required L5",
               "insufficient_clearance", "required_roles", "session L1")


def _restricted_leaked(resp_json: dict) -> bool:
    """True if ANY restricted content OR ACL metadata appears ANYWHERE in the response.

    Scans json.dumps(response) — covers answer, citations, AND any governance_trail/
    ACL field, so the metadata-disclosure class (denied-doc id, required roles/
    clearance) is caught, not just answer+citations.
    """
    blob = json.dumps(resp_json, default=str)
    if RESTRICTED_TEXT in blob:
        return True
    return any(marker in blob for marker in ACL_MARKERS)


@pytest.fixture(scope="module")
def client(request):
    # high rate-limit so the shared client isn't self-throttled across many tests;
    # the dedicated rate-limit test builds its own low-cap client.
    import os
    os.environ["RAG_RATE_LIMIT_PER_MIN"] = "100000"
    os.environ["RAG_QUERY_CAP_PER_DAY"] = "1000000"
    request.addfinalizer(lambda: (os.environ.pop("RAG_RATE_LIMIT_PER_MIN", None),
                                  os.environ.pop("RAG_QUERY_CAP_PER_DAY", None)))
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


def test_denied_caller_gets_no_acl_metadata_trail(client):
    """CRITICAL (the trail-disclosure bug): a denied INTERN's response must carry NO
    operator-only ACL metadata — no governance_trail, no required_roles, no denied-doc
    id, no required-clearance reason. Only a withheld COUNT.

    BITES: leave the full governance_trail (with required_roles/denied ids) in the
    client response -> the whole-response scan catches the ACL disclosure -> fails.
    """
    # a UNIQUE question so it's a cache MISS (a hit returns an empty trail -> the
    # withheld COUNT would be lost; the security assertion holds either way, but we
    # want the count populated to assert on it).
    r = _ask(client, "exec compensation schedule detail metadata-disclosure probe",
             roles="INTERN", clearance=1)
    assert r.status_code == 200
    j = r.json()
    assert "governance_trail" not in j      # no operator-only field on the client model
    assert not _restricted_leaked(j), "ACL metadata disclosed to a denied caller"
    assert j.get("n_withheld", 0) >= 1      # client learns a COUNT (UI: "N withheld")


def test_n_withheld_is_a_count_only(client):
    r = _ask(client, "exec compensation withheld count probe unique query",
             roles="INTERN", clearance=1)
    j = r.json()
    assert isinstance(j["n_withheld"], int) and j["n_withheld"] >= 1
    # the client model exposes only the redacted field set — no ACL fields.
    assert set(j.keys()) <= {"query", "answer", "architecture", "citations",
                             "access_denied", "admitted", "n_withheld"}


def test_clearance_out_of_range_is_4xx_not_500(client):
    for bad in ("99", "-3", "6", "1000"):
        r = client.post("/query", json={"question": "hi"}, headers={
            "X-User-Id": "t", "X-User-Roles": "PUBLIC", "X-Clearance": bad})
        assert r.status_code == 422, f"X-Clearance={bad} should be 4xx, got {r.status_code}"


def test_clearance_non_int_is_4xx(client):
    r = client.post("/query", json={"question": "hi"}, headers={
        "X-User-Id": "t", "X-User-Roles": "PUBLIC", "X-Clearance": "notanumber"})
    assert 400 <= r.status_code < 500


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


def test_rate_limit_returns_429_over_http(monkeypatch):
    # GATE B over the wire: a low per-min cap -> the Nth+1 request gets HTTP 429.
    monkeypatch.setenv("RAG_RATE_LIMIT_PER_MIN", "2")
    monkeypatch.setenv("RAG_QUERY_CAP_PER_DAY", "1000")
    from rag_engine.api import app
    with TestClient(app) as c:
        h = {"X-User-Id": "abuser", "X-User-Roles": "PUBLIC", "X-Clearance": "0"}
        assert c.post("/query", json={"question": "hi"}, headers=h).status_code == 200
        assert c.post("/query", json={"question": "hi"}, headers=h).status_code == 200
        r = c.post("/query", json={"question": "hi"}, headers=h)
        assert r.status_code == 429   # 3rd within the minute -> rate-limited


def test_startup_refuses_live_source_in_synthetic_profile(monkeypatch):
    # GATE B refuse-to-start: a live LLM credential under the synthetic profile must
    # prevent the app from starting (lifespan raises).
    monkeypatch.setenv("GROQ_API_KEY", "sk-live-demo-key")
    monkeypatch.setenv("RAG_DEMO_PROFILE", "synthetic")
    from rag_engine.api import app
    with pytest.raises(RuntimeError, match="SYNTHETIC-ONLY"):
        with TestClient(app):
            pass

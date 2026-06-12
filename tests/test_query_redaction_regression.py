"""G1 regression guard — /query STAYS redacted (the ACL-disclosure fix must not regress).

Adding /trace must not change /query: it still returns the ClientRAGResponse with NO
governance_trail / ACL detail (the P0.11b trail-disclosure fix). This is the guard.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ACL_MARKERS = ("governance_trail", "required_roles", "required L5",
               "insufficient_clearance", "hr-exec-comp", "HR_ADMIN")


@pytest.fixture(scope="module")
def client(request):
    import os
    os.environ["RAG_RATE_LIMIT_PER_MIN"] = "100000"
    request.addfinalizer(lambda: os.environ.pop("RAG_RATE_LIMIT_PER_MIN", None))
    from rag_engine.api import app
    with TestClient(app) as c:
        yield c


def test_query_response_has_no_trail(client):
    r = client.post("/query", json={"question": "what is the executive compensation schedule"},
                    headers={"X-User-Id": "i", "X-User-Roles": "INTERN", "X-Clearance": "1"})
    assert r.status_code == 200
    j = r.json()
    assert "governance_trail" not in j
    # the client model field set only (no ACL fields)
    assert set(j) <= {"query", "answer", "architecture", "citations", "access_denied",
                      "admitted", "n_withheld"}


def test_query_denied_persona_no_acl_metadata_anywhere(client):
    # a UNIQUE question -> cache MISS, so the trail-derived n_withheld is populated (a
    # cache hit returns an empty trail -> the count is lost, harmless; the security
    # assertion holds either way).
    r = client.post("/query",
                    json={"question": "exec compensation schedule acl-regression probe unique"},
                    headers={"X-User-Id": "i2", "X-User-Roles": "INTERN", "X-Clearance": "1"})
    blob = json.dumps(r.json())
    for marker in ACL_MARKERS:
        assert marker not in blob, f"ACL disclosure regressed: {marker!r} in /query response"
    assert r.json().get("n_withheld", 0) >= 1


def test_query_customer_pii_masked_not_raw(client):
    # the G0 class-D doc: an L2 analyst's /query answer must not contain raw PII.
    r = client.post("/query", json={"question": "customer account record dana"},
                    headers={"X-User-Id": "a", "X-User-Roles": "DATA_ANALYST,EMPLOYEE",
                             "X-Clearance": "2"})
    assert "dana.okafor@example.com" not in r.text

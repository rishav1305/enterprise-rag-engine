"""G1 — /trace + /trace/catalog endpoint shape, synthetic-only, rate-limit, clamp.

/trace is the glass-box endpoint (synthetic-only, since a trace surfaces governance
internals). /trace/catalog is the read-only estate. Both mirror /query's guards.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client(request):
    import os
    os.environ["RAG_RATE_LIMIT_PER_MIN"] = "100000"
    os.environ["RAG_QUERY_CAP_PER_DAY"] = "1000000"
    request.addfinalizer(lambda: (os.environ.pop("RAG_RATE_LIMIT_PER_MIN", None),
                                  os.environ.pop("RAG_QUERY_CAP_PER_DAY", None)))
    from rag_engine.api import app
    with TestClient(app) as c:
        yield c


def _trace(client, q, roles="INTERN", clearance=1):
    return client.post("/trace", json={"question": q}, headers={
        "X-User-Id": "t", "X-User-Roles": roles, "X-Clearance": str(clearance)})


def test_trace_returns_full_shape(client):
    r = _trace(client, "what is the executive compensation schedule", "C_SUITE", 5)
    assert r.status_code == 200
    t = r.json()
    # the normative Trace shape
    assert set(t) == {"query_dissection", "stages", "governance", "result"}
    d = t["query_dissection"]
    assert set(d) >= {"raw", "key_terms", "embedding_preview", "embedding_dim",
                      "intent_shape", "detected_topic"}
    assert len(d["embedding_preview"]) == 8
    assert t["stages"] and all({"id", "layer", "takes", "does", "pushes_out",
                                "duration_ms", "status", "substeps", "drilldown"}
                               <= set(s) for s in t["stages"])
    assert all({"title", "decision", "gate_fired", "reason", "required_level",
                "required_roles"} <= set(g) for g in t["governance"])
    assert {"answer", "citations", "admitted", "n_withheld", "access_denied"} \
        <= set(t["result"])


def test_trace_governance_has_real_decisions(client):
    r = _trace(client, "what is the executive compensation schedule", "INTERN", 1)
    decisions = {g["decision"] for g in r.json()["governance"]}
    assert decisions <= {"allow", "mask", "partial", "deny"}
    assert "deny" in decisions   # the intern is denied the exec-comp doc


def test_trace_clearance_out_of_range_422(client):
    r = client.post("/trace", json={"question": "hi"}, headers={
        "X-User-Id": "t", "X-User-Roles": "PUBLIC", "X-Clearance": "99"})
    assert r.status_code == 422


def test_trace_catalog_shape(client):
    r = client.get("/trace/catalog")
    assert r.status_code == 200
    sources = r.json()["sources"]
    assert len(sources) >= 23
    for s in sources:
        assert {"name", "type", "scale_badge", "sensitivity_class", "clearance_level",
                "provenance_url", "live_queryable", "synthetic"} <= set(s)
    # the live demo docs are flagged live_queryable; the PB-tail sources are catalog-only
    assert any(s["live_queryable"] for s in sources)
    assert any(not s["live_queryable"] for s in sources)


def test_trace_refuses_non_synthetic_profile():
    # under a 'production' profile, /trace must REFUSE (a trace surfaces governance
    # internals — never against real data).
    import os
    os.environ["RAG_DEMO_PROFILE"] = "production"
    os.environ["GROQ_API_KEY"] = "x"   # would also block startup; remove for the test
    try:
        # build a config-only app state to exercise the per-request guard directly.
        from rag_engine.api import _require_synthetic, _state
        from rag_engine.config import EngineConfig
        _state["config"] = EngineConfig()
        with pytest.raises(Exception):
            _require_synthetic()
    finally:
        os.environ.pop("RAG_DEMO_PROFILE", None)
        os.environ.pop("GROQ_API_KEY", None)
        _state.pop("config", None)


def test_trace_rate_limit_returns_429(monkeypatch):
    # FIX3: the /trace rate-limit must be enforced (removing the limiter from
    # _guarded_session would otherwise pass the suite silently).
    monkeypatch.setenv("RAG_RATE_LIMIT_PER_MIN", "2")
    monkeypatch.setenv("RAG_QUERY_CAP_PER_DAY", "1000")
    from rag_engine.api import app
    with TestClient(app) as c:
        h = {"X-User-Id": "abuser", "X-User-Roles": "PUBLIC", "X-Clearance": "0"}
        assert c.post("/trace", json={"question": "hi"}, headers=h).status_code == 200
        assert c.post("/trace", json={"question": "hi"}, headers=h).status_code == 200
        r = c.post("/trace", json={"question": "hi"}, headers=h)
        assert r.status_code == 429   # 3rd within the minute -> rate-limited


def test_trace_catalog_403_under_production(monkeypatch):
    # FIX3: /trace/catalog must REFUSE (403) over HTTP under a non-synthetic profile.
    # (The startup synthetic guard would refuse to BOOT with a live cred, so we set the
    # profile to production WITHOUT a live cred so the app boots, then assert the
    # per-request guard 403s.)
    monkeypatch.setenv("RAG_DEMO_PROFILE", "production")
    from rag_engine.api import app
    with TestClient(app) as c:
        assert c.get("/trace/catalog").status_code == 403
        r = c.post("/trace", json={"question": "hi"},
                   headers={"X-User-Id": "t", "X-User-Roles": "PUBLIC", "X-Clearance": "0"})
        assert r.status_code == 403

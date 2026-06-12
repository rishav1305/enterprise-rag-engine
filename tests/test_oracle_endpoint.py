"""G4 — GET /oracle: the LIVE 210-cell leak oracle endpoint.

Asserts the endpoint returns the real grid (210 cells / 0 leaks), is leak-safe
(booleans + labels only, never content), synthetic-only, and — the bite — that if
the engine ever over-reveals on a cell, that cell flips ``leaked: true`` and the
leak total increments. The grid is computed by driving access.evaluate per cell
(the SAME check as tests/test_leak_oracle.py), not a hardcoded all-green.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client(request):
    import os

    os.environ["RAG_RATE_LIMIT_PER_MIN"] = "100000"
    os.environ["RAG_QUERY_CAP_PER_DAY"] = "1000000"
    request.addfinalizer(
        lambda: (
            os.environ.pop("RAG_RATE_LIMIT_PER_MIN", None),
            os.environ.pop("RAG_QUERY_CAP_PER_DAY", None),
        )
    )
    from rag_engine.api import app

    with TestClient(app) as c:
        yield c


def test_oracle_returns_210_cells_zero_leaks(client):
    r = client.get("/oracle", headers={"X-User-Id": "t"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"cells", "personas", "classes", "totals"}
    assert body["totals"] == {"cells": 210, "leaks": 0}
    assert len(body["cells"]) == 210
    assert len(body["personas"]) == 15
    assert len(body["classes"]) == 14
    # 15 personas x 14 classes, no dupes
    keys = {(c["persona"], c["sensitivity_class"]) for c in body["cells"]}
    assert len(keys) == 210
    # every cell carries a real decision + a leaked bool
    for c in body["cells"]:
        assert c["decision"] in {"allow", "mask", "partial", "deny"}
        assert isinstance(c["leaked"], bool)
        assert c["leaked"] is False  # the gate: 0 leaks


def test_oracle_is_leak_safe_no_content(client):
    """The response must carry NO content/PII — only labels, decisions, booleans."""
    r = client.get("/oracle", headers={"X-User-Id": "t"})
    cell = r.json()["cells"][0]
    # exactly the leak-safe metadata keys; no 'content'/'quote'/'answer'/'text'
    assert set(cell) == {
        "persona",
        "persona_label",
        "clearance_level",
        "sensitivity_class",
        "class_label",
        "decision",
        "expected",
        "leaked",
    }
    for banned in ("content", "quote", "answer", "text", "row", "pii"):
        assert banned not in cell


def test_oracle_bite_engine_over_reveal_flips_a_cell_red(monkeypatch):
    """MUTATION: if the engine over-reveals on a cell the ground truth denies, that
    cell must flip leaked=true and the leak total must rise. Proves the grid reflects
    the real engine decision, not a static green."""
    from rag_engine.catalog import oracle as oracle_mod
    from rag_engine.governance.access import evaluate as real_evaluate

    # intern x F (exec comp) is genuinely denied. Force the ENGINE to "allow" it.
    def leaky_evaluate(chunk, session):
        if getattr(chunk.security, "sensitivity_class", None) == "F" and session.user_id == "intern":
            base = real_evaluate(chunk, session)
            return base.model_copy(update={"decision": "allow", "reason": "MUTATED-for-test"})
        return real_evaluate(chunk, session)

    monkeypatch.setattr(oracle_mod, "evaluate", leaky_evaluate)
    grid = oracle_mod.build_oracle_grid()

    assert grid["totals"]["leaks"] >= 1, "mutation did not produce a leak — the grid is not live"
    intern_f = [c for c in grid["cells"] if c["persona"] == "intern" and c["sensitivity_class"] == "F"][0]
    assert intern_f["decision"] == "allow"
    assert intern_f["expected"] == "deny"
    assert intern_f["leaked"] is True

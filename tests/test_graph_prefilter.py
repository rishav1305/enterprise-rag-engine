"""WORKER-A hardened test — graph mode drops denied nodes at the traversal.

A denied node is NEVER in the graph retriever's candidate set for an under-cleared
session, asserted on the retriever output (BEFORE any L5 post-filter). Bites if
the allowlist pre-filter is bypassed: the faithful FakeModeStore honours
``id IN $allow``, so a retriever that traverses without the allowlist leaks the
denied neighbour and this test fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _mode_fakes import FakeAclSource, FakeModeStore, chunk  # noqa: E402

from rag_engine.retrieval.graph_mode import GraphRetriever  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402


def _setup():
    # n1 (public) links to n2 (public, allowed) AND n_denied (exec-comp, DENIED).
    c1, _, _ = chunk("n1", cls="B", level=1)
    c2, _, _ = chunk("n2", cls="B", level=1)
    cd, _, _ = chunk("n_denied", cls="F", level=5, ntk=["C_SUITE"])
    source = FakeAclSource([c1, c2, cd])
    store = FakeModeStore(
        rows={"n1": {"asset": "a1", "text": "meridian"},
              "n2": {"asset": "a1", "text": "meridian"},
              "n_denied": {"asset": "a1", "text": "meridian"}},
        edges={"n1": ["n2", "n_denied"]},
    )
    return GraphRetriever(store, source)


def test_denied_node_never_in_graph_candidate_set():
    retriever = _setup()
    analyst = Session(user_id="a", roles=["EMPLOYEE"], clearance_level=2)
    rows = retriever.retrieve_for_session("n1", analyst)
    ids = {r["id"] for r in rows}
    assert "chunk:n_denied" not in ids   # denied neighbour excluded at traversal
    assert "chunk:n2" in ids             # authorized neighbour kept


def test_graph_empty_allowlist_fail_closed():
    retriever = _setup()
    # a session that can see NOTHING (no roles, clearance 0) -> empty allowlist
    nobody = Session(user_id="x", roles=[], clearance_level=0)
    # public n2 is class-B level-1 -> still visible; use a denied-only graph instead:
    cd, _, _ = chunk("only_denied", cls="F", level=5, ntk=["C_SUITE"])
    src = FakeAclSource([cd])
    store = FakeModeStore(rows={"only_denied": {"asset": "a1", "text": "m"}},
                          edges={"only_denied": []})
    r = GraphRetriever(store, src)
    assert r.retrieve_for_session("only_denied", nobody) == []

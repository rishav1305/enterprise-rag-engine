"""WORKER-B hardened test — structured/SQL mode drops denied rows at query time.

A denied asset's/chunk's rows are NEVER in the structured retriever's candidate
set for an under-cleared session, asserted on the retriever output (BEFORE the
P0.3b result-masking and the L5 post-filter). Bites if the allowlist pre-filter
is bypassed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _mode_fakes import FakeAclSource, FakeModeStore, chunk  # noqa: E402

from rag_engine.retrieval.structured_mode import StructuredRetriever  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402


def _setup():
    c1, _, _ = chunk("r1", cls="B", level=1)
    cd, _, _ = chunk("r_denied", cls="F", level=5, ntk=["C_SUITE"])
    source = FakeAclSource([c1, cd])
    store = FakeModeStore(
        rows={"r1": {"asset": "a1", "text": "meridian"},
              "r_denied": {"asset": "a1", "text": "meridian"}},
        edges={},
    )
    return StructuredRetriever(store, source)


def test_denied_row_never_in_structured_candidate_set():
    retriever = _setup()
    analyst = Session(user_id="a", roles=["EMPLOYEE"], clearance_level=2)
    rows = retriever.retrieve_for_session("a1", analyst)
    ids = {r["id"] for r in rows}
    assert "chunk:r_denied" not in ids   # denied row excluded at query time
    assert "chunk:r1" in ids             # authorized row kept


def test_structured_empty_allowlist_fail_closed():
    cd, _, _ = chunk("only_denied", cls="F", level=5, ntk=["C_SUITE"])
    src = FakeAclSource([cd])
    store = FakeModeStore(rows={"only_denied": {"asset": "a1", "text": "m"}}, edges={})
    r = StructuredRetriever(store, src)
    nobody = Session(user_id="x", roles=[], clearance_level=0)
    assert r.retrieve_for_session("a1", nobody) == []

"""WORKER-C hardened test — lexical/full-text mode drops denied hits at query time.

A full-text hit on denied content is NEVER in the lexical retriever's candidate
set for an under-cleared session, asserted on the retriever output (BEFORE the L5
post-filter). Bites if the allowlist pre-filter is bypassed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _mode_fakes import FakeAclSource, FakeModeStore, chunk  # noqa: E402

from rag_engine.retrieval.lexical_mode import LexicalRetriever  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402


def _setup():
    # both chunks contain "meridian" so an unfiltered BM25 search would surface both
    c1, _, _ = chunk("d1", cls="B", level=1, text="meridian quarterly report")
    cd, _, _ = chunk("d_denied", cls="F", level=5, ntk=["C_SUITE"],
                     text="meridian exec compensation")
    source = FakeAclSource([c1, cd])
    store = FakeModeStore(
        rows={"d1": {"asset": "a1", "text": "meridian quarterly report"},
              "d_denied": {"asset": "a1", "text": "meridian exec compensation"}},
        edges={},
    )
    return LexicalRetriever(store, source)


def test_denied_hit_never_in_lexical_candidate_set():
    retriever = _setup()
    analyst = Session(user_id="a", roles=["EMPLOYEE"], clearance_level=2)
    rows = retriever.retrieve_for_session("meridian", analyst)
    ids = {r["id"] for r in rows}
    assert "chunk:d_denied" not in ids   # denied full-text hit excluded
    assert "chunk:d1" in ids             # authorized hit kept


def test_lexical_empty_allowlist_fail_closed():
    cd, _, _ = chunk("only_denied", cls="F", level=5, ntk=["C_SUITE"], text="meridian")
    src = FakeAclSource([cd])
    store = FakeModeStore(rows={"only_denied": {"asset": "a1", "text": "meridian"}},
                          edges={})
    r = LexicalRetriever(store, src)
    nobody = Session(user_id="x", roles=[], clearance_level=0)
    assert r.retrieve_for_session("meridian", nobody) == []

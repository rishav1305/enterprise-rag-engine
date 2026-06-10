"""P0.6 Task 1 — SurrealStore per-mode retrieve methods are allowlist-scoped.

The store-level guarantee the three mode retrievers build on: graph_neighbors /
structured_rows / fulltext_search each DROP any chunk id not in the passed
allowlist AT QUERY TIME (id IN $allow), and an EMPTY allowlist returns nothing
(fail-closed). Uses the ephemeral surreal_local fixture; skips cleanly without
the binary/SDK.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _seed(st):
    """Seed 3 chunks (n1,n2 authorized; n_denied not) + a graph edge + text.

    n1 links to BOTH n2 and n_denied; all three share asset 'a1' and contain the
    word 'meridian' so every mode would surface n_denied if unfiltered.
    """
    for cid in ("n1", "n2", "n_denied"):
        st.upsert_chunk({
            "chunk_id": cid, "asset_id": "a1", "cls": "B", "level": 1,
            "text": f"meridian timeout shard {cid}",
        })
    st.relate_chunks("n1", "n2")
    st.relate_chunks("n1", "n_denied")


def test_store_modes_scope_by_allowlist(surreal_local):
    from rag_engine.store.surreal import SurrealStore
    st = SurrealStore(dsn=surreal_local["dsn"], ns=surreal_local["ns"],
                      db=surreal_local["db"], user=surreal_local["user"],
                      password=surreal_local["pass"])
    st.connect()
    st.apply_schema()
    _seed(st)

    allow = ["n1", "n2"]   # n_denied is NOT authorized

    g = {str(r.get("id")) for r in st.graph_neighbors("n1", allow)}
    assert not any("n_denied" in i for i in g)      # denied neighbour dropped
    assert any("n2" in i for i in g)                # authorized neighbour kept

    s = {str(r.get("id")) for r in st.structured_rows("a1", allow)}
    assert not any("n_denied" in i for i in s)      # denied row dropped
    assert any("n1" in i for i in s) or any("n2" in i for i in s)

    f = {str(r.get("id")) for r in st.fulltext_search("meridian", allow)}
    assert not any("n_denied" in i for i in f)      # denied full-text hit dropped
    assert len(f) >= 1                              # authorized hits surface


def test_store_modes_empty_allowlist_fail_closed(surreal_local):
    from rag_engine.store.surreal import SurrealStore
    st = SurrealStore(dsn=surreal_local["dsn"], ns=surreal_local["ns"],
                      db=surreal_local["db"], user=surreal_local["user"],
                      password=surreal_local["pass"])
    st.connect()
    st.apply_schema()
    _seed(st)
    assert st.graph_neighbors("n1", []) == []
    assert st.structured_rows("a1", []) == []
    assert st.fulltext_search("meridian", []) == []

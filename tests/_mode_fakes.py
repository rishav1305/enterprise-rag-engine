"""Shared fakes for the P0.6 per-mode pre-filter tests.

``FakeModeStore`` faithfully honours the allowlist exactly as the real
SurrealStore does (``id IN $allow``) — so the hardened tests prove the RETRIEVER
derives and passes the correct allowlist. If a retriever bypassed the pre-filter
(e.g. passed every id), the denied item would leak through this faithful store
and the test would fail. ``FakeAclSource`` supplies the chunk ACLs the allowlist
is derived from.
"""

from __future__ import annotations

from rag_engine.schemas import EnrichedChunk, SecurityContext


def chunk(cid, cls="B", level=1, ntk=None, text="meridian timeout shard", asset="a1"):
    return EnrichedChunk(
        chunk_id=cid, parent_doc_id=cid, parent_title="t", content=text,
        security=SecurityContext(allowed_roles=ntk or [], clearance_level=level,
                                 sensitivity_class=cls, need_to_know_roles=ntk or []),
    ), asset, text


class FakeAclSource:
    """all_chunk_security() -> the EnrichedChunks the allowlist is derived from."""

    def __init__(self, chunks):
        self._chunks = chunks

    def all_chunk_security(self):
        return self._chunks


class FakeModeStore:
    """Honours the allowlist exactly like SurrealStore (id IN $allow).

    Seeded with (chunk_id -> {asset, text, neighbours}). Each query method returns
    ONLY rows whose id is in ``allow`` — so a retriever that fails to pre-filter
    leaks the denied id and the hardened test fails.
    """

    def __init__(self, rows, edges):
        # rows: {cid: {"asset": str, "text": str}}; edges: {src: [dst,...]}
        self._rows = rows
        self._edges = edges

    def graph_neighbors(self, node_chunk_id, allow):
        allow = set(allow)
        return [
            {"id": f"chunk:{cid}", **self._rows[cid]}
            for cid in self._edges.get(node_chunk_id, [])
            if cid in allow                      # id IN $allow
        ]

    def structured_rows(self, asset_id, allow):
        allow = set(allow)
        return [
            {"id": f"chunk:{cid}", **r}
            for cid, r in self._rows.items()
            if r["asset"] == asset_id and cid in allow   # asset match AND id IN $allow
        ]

    def fulltext_search(self, query, allow):
        allow = set(allow)
        return [
            {"id": f"chunk:{cid}", **r}
            for cid, r in self._rows.items()
            if query in r["text"] and cid in allow       # text match AND id IN $allow
        ]

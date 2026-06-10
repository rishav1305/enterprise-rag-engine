"""SurrealStore — the SurrealDB-backed unified store (P0.2a).

Wraps a SurrealDB connection (DSN/creds from config) and is the one place that
speaks SurrealQL. The SAME instance serves catalog + ACLs + the four retrieval
modes; this class is the seam P0.2b (vectors-by-id) and P0.3 (graph/SurrealQL/
full-text query wiring) build on. TurboVec keeps the vector ANN (per spike S2).

Multi-setup: identical code for a local self-host instance (CI/dev) and
SurrealDB Cloud — only the DSN/creds differ (CONFIGURABLE).
"""

from __future__ import annotations

from typing import Any

from .schema import VECTOR_DIM, ddl_statements


class SurrealStore:
    def __init__(self, dsn: str, ns: str, db: str, user: str, password: str) -> None:
        self.dsn = dsn
        self.ns = ns
        self.db = db
        self.user = user
        self.password = password
        self._db: Any = None

    def connect(self) -> None:
        from surrealdb import Surreal

        self._db = Surreal(self.dsn)
        self._db.signin({"username": self.user, "password": self.password})
        self._db.use(self.ns, self.db)

    def apply_schema(self, vector_dim: int = VECTOR_DIM) -> None:
        for stmt in ddl_statements(vector_dim):
            self._db.query(stmt)

    # ---- catalog assets ------------------------------------------------
    @staticmethod
    def _asset_rid(asset_id: str):
        from surrealdb import RecordID

        return RecordID("asset", asset_id)

    def upsert_asset(self, asset: dict[str, Any]) -> None:
        """Idempotent upsert keyed by asset_id (UPSERT = update-or-create).

        The record-id is bound as a parameter (not string-interpolated) — SECURE:
        no SurrealQL injection via asset_id.
        """
        content = {k: v for k, v in asset.items() if k != "asset_id"}
        self._db.query(
            "UPSERT $rid CONTENT $data;",
            {"rid": self._asset_rid(asset["asset_id"]), "data": content},
        )

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        # SDK 2.0.0 query() returns the row list directly (not per-statement-wrapped).
        rows = self._db.query("SELECT * FROM $rid;", {"rid": self._asset_rid(asset_id)})
        return rows[0] if rows else None

    def all_assets(self) -> list[dict[str, Any]]:
        rows = self._db.query("SELECT * FROM asset;")
        return list(rows) if rows else []

    def count_assets(self) -> int:
        return len(self.all_assets())

    # ---- chunks (vectors-by-id live here; TurboVec serves the ANN) ------
    @staticmethod
    def _chunk_rid(chunk_id: str):
        from surrealdb import RecordID

        # chunk_id is a bare key (e.g. "wikipedia_kb-000123"); record-id param-bound.
        return RecordID("chunk", chunk_id)

    def upsert_chunk(self, chunk: dict[str, Any]) -> None:
        """Idempotent upsert of a chunk (text + vector + asset_id + ACL fields).

        The id is bound as a RecordID param (no injection — SECURE).
        """
        content = {k: v for k, v in chunk.items() if k != "chunk_id"}
        self._db.query(
            "UPSERT $rid CONTENT $data;",
            {"rid": self._chunk_rid(chunk["chunk_id"]), "data": content},
        )

    def count_chunks(self) -> int:
        rows = self._db.query("SELECT count() AS n FROM chunk GROUP ALL;")
        return int(rows[0]["n"]) if rows else 0

    def delete_chunk(self, chunk_id: str) -> None:
        """Remove a chunk (P0.9 CDC delete propagation).

        After this the chunk is gone from get_chunk_row, chunk_security_rows (the
        allowlist source), and all 3 mode queries — so it is UN-retrievable. The
        chunk's ``links`` graph edges go too: SurrealDB CASCADE-deletes RELATION
        edges when their endpoint node is removed (verified — a node-only delete
        leaves zero orphaned links rows), so deleting the node is sufficient. We
        keep an explicit defensive edge-sweep as belt-and-suspenders in case a
        non-RELATION ``links`` row ever exists; the cascade is the primary mechanism
        (the `test_delete_chunk_removes_graph_edges` test asserts the END STATE — no
        edge references the deleted chunk — regardless of which mechanism cleaned it).
        RecordID-bound (SECURE). Idempotent: deleting a missing chunk is a no-op.
        """
        rid = self._chunk_rid(chunk_id)
        # node delete first — RELATION edges cascade with it. The explicit sweeps
        # below are a harmless backstop for any stray non-cascading edge row.
        self._db.query("DELETE $rid;", {"rid": rid})
        self._db.query("DELETE links WHERE in = $rid OR out = $rid;", {"rid": rid})

    def get_chunk_row(self, chunk_id: str) -> dict[str, Any] | None:
        """Full chunk row (text + asset_id + cls + level + vec) by id, or None."""
        rows = self._db.query("SELECT * FROM $rid;", {"rid": self._chunk_rid(chunk_id)})
        return rows[0] if rows else None

    def chunks_by_version(self, embedder_version: str) -> list[dict[str, Any]]:
        """Chunk rows whose embedder_version matches (P0.9 re-embed migration).

        Used by the ReEmbedder to find the chunks still on an old embedding version
        so re-embedding is resumable + only touches stale rows. Param-bound (SECURE).
        """
        rows = self._db.query(
            "SELECT * FROM chunk WHERE embedder_version = $ev;",
            {"ev": embedder_version},
        )
        return list(rows) if rows else []

    def relate_chunks(self, src_chunk_id: str, dst_chunk_id: str) -> None:
        """Create a directed ``links`` graph edge between two chunks (P0.6 graph).

        Record-ids bound as params (SECURE — no injection via chunk ids).
        """
        self._db.query(
            "RELATE $src->links->$dst;",
            {"src": self._chunk_rid(src_chunk_id), "dst": self._chunk_rid(dst_chunk_id)},
        )

    # ---- P0.6: per-mode retrieval, allowlist PRE-filtered -----------------
    # Every mode scopes its query by the session's allowlist of chunk ids so an
    # unauthorized item is never even a candidate (drop-before-search) — the same
    # invariant the vector mode gets from the TurboVec allowlist. The allowlist is
    # bound as RecordID params (SECURE). An EMPTY allowlist returns NOTHING
    # (fail-closed): `id IN []` matches nothing.
    def _allow_rids(self, allow: list[str]) -> list[Any]:
        return [self._chunk_rid(cid) for cid in allow]

    def graph_neighbors(self, node_chunk_id: str, allow: list[str]) -> list[dict[str, Any]]:
        """Chunks reachable from ``node_chunk_id`` over ``links``, allowlist-scoped.

        A denied neighbour is never returned — the traversal result is filtered by
        ``id IN $allow`` at query time (not post-hoc), so the pre-filter holds even
        if a caller forgets the post-filter. Fail-closed on empty allowlist.
        """
        if not allow:
            return []
        rows = self._db.query(
            "SELECT * FROM $node->links->chunk WHERE id IN $allow;",
            {"node": self._chunk_rid(node_chunk_id), "allow": self._allow_rids(allow)},
        )
        return list(rows) if rows else []

    def structured_rows(self, asset_id: str, allow: list[str]) -> list[dict[str, Any]]:
        """Chunk rows for ``asset_id``, allowlist-scoped (P0.6 structured mode).

        Rows from a denied asset/chunk are excluded at query time — a denied
        asset's rows are NEVER returned, independent of (and before) the P0.3b
        result-masking that still applies downstream. Fail-closed on empty allowlist.
        """
        if not allow:
            return []
        rows = self._db.query(
            "SELECT * FROM chunk WHERE asset_id = $asset AND id IN $allow;",
            {"asset": asset_id, "allow": self._allow_rids(allow)},
        )
        return list(rows) if rows else []

    def fulltext_search(self, query: str, allow: list[str]) -> list[dict[str, Any]]:
        """BM25 full-text hits over chunk text, allowlist-scoped (P0.6 lexical mode).

        A full-text hit on denied content is excluded at query time (``id IN
        $allow``), so a lexical match on an unauthorized chunk is never a
        candidate. Fail-closed on empty allowlist.
        """
        if not allow:
            return []
        rows = self._db.query(
            "SELECT * FROM chunk WHERE text @@ $q AND id IN $allow;",
            {"q": query, "allow": self._allow_rids(allow)},
        )
        return list(rows) if rows else []

    def chunk_security_rows(self) -> list[dict[str, Any]]:
        """PROJECTED rows for the allowlist pass — ids + ACLs ONLY (no text/vec).

        ELASTIC: the allowlist scan must not drag full content/vector blobs per
        query; this projects just what governance needs (id, asset_id, cls, level).
        """
        rows = self._db.query("SELECT id, asset_id, cls, level FROM chunk;")
        return list(rows) if rows else []

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

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

    def get_chunk_row(self, chunk_id: str) -> dict[str, Any] | None:
        """Full chunk row (text + asset_id + cls + level + vec) by id, or None."""
        rows = self._db.query("SELECT * FROM $rid;", {"rid": self._chunk_rid(chunk_id)})
        return rows[0] if rows else None

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

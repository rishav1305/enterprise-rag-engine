"""Durable audit sink for governance events (P0.5, TRANSPARENT).

The ``chunk_source`` malformed-row drops were only ``logging.warning``-ed — a
real data-integrity signal that wasn't queryable. The audit sink makes such
governance events DURABLE + queryable: an ``InMemoryAuditSink`` for tests, a
``SurrealAuditSink`` (SurrealDB ``audit`` table) for production. Any code that
drops a row for governance reasons records an event here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Protocol


class AuditSink(Protocol):
    def record_event(self, kind: str, detail: dict[str, Any]) -> None: ...


def _event(kind: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "detail": dict(detail),
    }


class InMemoryAuditSink:
    """No-creds sink for tests — records every governance event."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record_event(self, kind: str, detail: dict[str, Any]) -> None:
        self.events.append(_event(kind, detail))

    def by_kind(self, kind: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["kind"] == kind]


class SurrealAuditSink:
    """Durable sink backed by a SurrealDB ``audit`` table (queryable)."""

    def __init__(self, store) -> None:
        self.store = store

    def record_event(self, kind: str, detail: dict[str, Any]) -> None:
        from surrealdb import RecordID

        ev = _event(kind, detail)
        self.store._db.query(
            "UPSERT $rid CONTENT $data;",
            {"rid": RecordID("audit", ev["id"]), "data": ev},
        )

    def query_kind(self, kind: str) -> list[dict[str, Any]]:
        rows = self.store._db.query(
            "SELECT * FROM audit WHERE kind = $k;", {"k": kind}
        )
        return list(rows) if rows else []

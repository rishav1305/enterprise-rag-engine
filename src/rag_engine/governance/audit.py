"""Lightweight append-only audit log for governance decisions.

In production this writes to an immutable sink (e.g. an append-only table or a
WORM bucket). Here it is an in-process list so tests and the demo can assert on
exactly what was allowed and blocked.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..schemas import GovernanceDecision, Session


class AuditLog:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, session: Session, query: str, trail: list[GovernanceDecision]) -> None:
        self.records.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "user_id": session.user_id,
                "roles": list(session.roles),
                "query": query,
                "allowed": [d.chunk_id for d in trail if d.decision == "allow"],
                "blocked": [
                    {"chunk_id": d.chunk_id, "reason": d.reason}
                    for d in trail
                    if d.decision == "deny"
                ],
            }
        )

    @property
    def blocked_count(self) -> int:
        return sum(len(r["blocked"]) for r in self.records)

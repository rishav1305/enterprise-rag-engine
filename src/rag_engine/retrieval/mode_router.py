"""ModeRouter — wires the P0.6 mode retrievers + AllowlistBackend (P0.11a W4).

When a SurrealDB store is configured, non-vector queries can be answered by the
graph / structured / lexical mode retrievers — each pre-filters denied content with
the SAME governance allowlist as the vector path (drop-before-search), via a
swappable ``AllowlistBackend`` chosen from config (in_process default, parity-
guaranteed ReBAC backends optional). The router holds one backend instance and the
three retrievers, and dispatches by query intent.
"""

from __future__ import annotations

from ..config import EngineConfig
from ..governance.allowlist import AllowlistBackend, InProcessAllowlist
from ..schemas import Session
from .graph_mode import GraphRetriever
from .lexical_mode import LexicalRetriever
from .structured_mode import StructuredRetriever


def build_allowlist_backend(config: EngineConfig) -> AllowlistBackend:
    """Construct the configured AllowlistBackend (in_process default).

    ReBAC backends are parity-guaranteed to agree with in_process (the canonical
    decision), so the choice changes lookup cost, never the decision. spicedb/oso
    require their gated deps + endpoints; local_rebac is zero-dep.
    """
    name = config.allowlist_backend
    if name == "in_process":
        return InProcessAllowlist()
    if name == "local_rebac":
        from ..governance.rebac import LocalReBACAllowlist

        return LocalReBACAllowlist()
    if name == "spicedb":  # pragma: no cover - gated
        from ..governance.rebac.spicedb import SpiceDBAllowlist
        import os

        return SpiceDBAllowlist(os.environ["SPICEDB_ENDPOINT"],
                                os.environ["SPICEDB_TOKEN"])
    if name == "oso":  # pragma: no cover - gated
        from ..governance.rebac.oso import OsoCloudAllowlist
        import os

        return OsoCloudAllowlist(os.getenv("OSO_URL", "https://cloud.osohq.com"),
                                 os.environ["OSO_AUTH"])
    raise ValueError(f"unknown allowlist_backend {name!r}")


class ModeRouter:
    def __init__(self, store, source, config: EngineConfig | None = None) -> None:
        cfg = config or EngineConfig()
        backend = build_allowlist_backend(cfg)
        self.backend = backend
        self.graph = GraphRetriever(store, source, backend=backend)
        self.structured = StructuredRetriever(store, source, backend=backend)
        self.lexical = LexicalRetriever(store, source, backend=backend)

    def graph_neighbors(self, node_chunk_id: str, session: Session) -> list[dict]:
        return self.graph.retrieve_for_session(node_chunk_id, session)

    def structured_rows(self, asset_id: str, session: Session) -> list[dict]:
        return self.structured.retrieve_for_session(asset_id, session)

    def lexical_search(self, query: str, session: Session) -> list[dict]:
        return self.lexical.retrieve_for_session(query, session)


__all__ = ["ModeRouter", "build_allowlist_backend"]

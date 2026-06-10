"""SemanticRouter — adaptive retrieval-mode routing via semantic-router (P0.3b).

Replaces/augments the regex ``HeuristicRouter`` with embedding-similarity routing
(spec §9). Crucially it uses a **deterministic LOCAL encoder** — our
``HashingEmbedder`` wrapped as a semantic-router ``DenseEncoder`` — so there is NO
LLM and NO API call in the hot path, and routing is reproducible in tests. The
cloud encoders (OpenAI/Cohere) remain available via semantic-router for a richer
production setup (multi-setup), but are never the default here.

Routes map NL queries to a ``RAGArchitecture`` retrieval mode:
  * sql/structured  -> ADVANCED_HYBRID (the warehouse text-to-SQL leg)
  * graph           -> GRAPH_RAG
  * lexical / multi -> AGENTIC_LOOP
  * vector (default)-> ADVANCED_HYBRID
"""

from __future__ import annotations

from .base import QueryRouter
from ..retrieval.embedders import HashingEmbedder
from ..schemas import RAGArchitecture

# route name -> retrieval-mode enum
_ROUTE_TO_ARCH = {
    "sql": RAGArchitecture.ADVANCED_HYBRID,      # warehouse structured / text-to-SQL
    "graph": RAGArchitecture.GRAPH_RAG,
    "lexical": RAGArchitecture.AGENTIC_LOOP,     # exact-id / multi-step
    "vector": RAGArchitecture.ADVANCED_HYBRID,
}

_DEFAULT_ROUTES = {
    "sql": ["average trip fare by borough last quarter",
            "total sales by segment last quarter",
            "sum of revenue grouped by region",
            "count transactions per merchant this month"],
    "graph": ["which supplier provided the recalled component",
              "trace the contract to its supplier and components",
              "what components are linked to this recall"],
    "lexical": ["error code ERR-DB-0042",
                "ticket MER-12345 status",
                "find the exact error identifier"],
    "vector": ["what is the remote work policy",
               "summarize the employee handbook",
               "explain the security guidelines"],
}


def _build_dense_encoder(dim: int):
    from semantic_router.encoders import DenseEncoder

    embedder = HashingEmbedder(dim=dim)

    class _HashingDenseEncoder(DenseEncoder):
        """Deterministic local DenseEncoder backed by HashingEmbedder (no creds)."""

        def __init__(self) -> None:
            super().__init__(name="hashing", score_threshold=0.0)

        def __call__(self, docs):
            return [embedder.embed([d])[0].tolist() for d in docs]

    return _HashingDenseEncoder()


class SemanticRouter(QueryRouter):
    def __init__(self, dim: int = 256, routes: dict[str, list[str]] | None = None) -> None:
        from semantic_router import Route
        from semantic_router.routers import SemanticRouter as _SRRouter

        self._routes_spec = routes or _DEFAULT_ROUTES
        route_objs = [Route(name=n, utterances=u) for n, u in self._routes_spec.items()]
        encoder = _build_dense_encoder(dim)
        self._router = _SRRouter(encoder=encoder, routes=route_objs, auto_sync="local")

    def route(self, query: str) -> RAGArchitecture:
        choice = self._router(query)
        name = getattr(choice, "name", None)
        # no confident route -> default to the vector/hybrid leg (fail-safe)
        return _ROUTE_TO_ARCH.get(name, RAGArchitecture.ADVANCED_HYBRID)

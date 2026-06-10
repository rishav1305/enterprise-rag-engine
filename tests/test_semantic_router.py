"""P0.3b WORKER-B — SemanticRouter classification + determinism (local encoder)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

pytest.importorskip("semantic_router")

from rag_engine.routing.semantic_router import SemanticRouter  # noqa: E402
from rag_engine.schemas import RAGArchitecture  # noqa: E402


@pytest.fixture(scope="module")
def router():
    return SemanticRouter()


def test_route_returns_architecture_enum(router):
    out = router.route("total sales by segment last quarter")
    assert isinstance(out, RAGArchitecture)


def test_deterministic_same_query_same_route(router):
    q = "error code ERR-DB-0042"
    assert router.route(q) == router.route(q)


def test_warehouse_query_routes_to_structured_leg(router):
    # warehouse-y NL -> the SQL/structured leg (ADVANCED_HYBRID)
    assert router.route("sum of revenue grouped by region") == RAGArchitecture.ADVANCED_HYBRID


def test_graph_query_routes_to_graph(router):
    assert router.route("trace the contract to its supplier and components") == \
        RAGArchitecture.GRAPH_RAG


def test_lexical_query_routes_to_agentic(router):
    assert router.route("ticket MER-12345 status") == RAGArchitecture.AGENTIC_LOOP


def test_no_confident_route_falls_back_to_hybrid():
    # When the underlying router returns NO confident route (name=None), route()
    # falls back to the vector/hybrid leg (fail-safe). We assert the EXACT default
    # by driving the mapping with a None-named choice, so a regression in the
    # `.get(name, ADVANCED_HYBRID)` default bites. Uses a FRESH router (not the
    # module fixture) so the monkeypatch can't leak into other tests.
    r = SemanticRouter()

    class _NoMatch:
        name = None

    r._router = lambda q: _NoMatch()
    assert r.route("anything") == RAGArchitecture.ADVANCED_HYBRID


def test_ood_query_still_returns_a_valid_architecture():
    # belt-and-suspenders: an out-of-distribution string returns SOME valid enum
    # (never crashes), even if the encoder weakly matches a route.
    r = SemanticRouter()
    assert isinstance(r.route("xyzzy plugh frobnicate qux"), RAGArchitecture)


def test_no_llm_in_hot_path():
    # the local encoder is deterministic + offline: constructing + routing makes no
    # network call (HashingEmbedder). Smoke: routing many queries is fast + stable.
    r = SemanticRouter()
    results = [r.route("total sales by region") for _ in range(5)]
    assert len(set(results)) == 1   # stable across repeats (no nondeterministic API)

"""The router maps the taxonomy to the right architecture, deterministically."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from rag_engine.routing.heuristic_router import HeuristicRouter
from rag_engine.schemas import RAGArchitecture

router = HeuristicRouter()


@pytest.mark.parametrize(
    "query,expected",
    [
        ("What is the remote work stipend?", RAGArchitecture.ADVANCED_HYBRID),
        ("How much does Premium cost?", RAGArchitecture.ADVANCED_HYBRID),
        ("What is the relationship between margin and runway?", RAGArchitecture.GRAPH_RAG),
        ("Compare CEO and CFO compensation across the schedule", RAGArchitecture.GRAPH_RAG),
        ("First find revenue and then reconcile it against runway step by step",
         RAGArchitecture.AGENTIC_LOOP),
        ("What is revenue? And what is the operating income?", RAGArchitecture.AGENTIC_LOOP),
    ],
)
def test_routing(query, expected):
    assert router.route(query) == expected

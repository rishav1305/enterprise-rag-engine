"""Deterministic intent gate run *before* hitting the database clusters.

A cheap regex/keyword classifier is the right default here: it is transparent,
testable, has zero latency cost, and never burns a model call just to decide
which retriever to use. Replace with a fine-tuned classifier behind the same
``QueryRouter`` ABC when you have labelled traffic.

Routing map (matches the taxonomy):
  * single-hop factual lookup        -> ADVANCED_HYBRID
  * relationship / cross-entity      -> GRAPH_RAG
  * multi-step, multi-hop reasoning  -> AGENTIC_LOOP
"""

from __future__ import annotations

import re

from ..schemas import RAGArchitecture
from .base import QueryRouter

_RELATIONSHIP = re.compile(
    r"\b(relationship|related|connection|connected|compare|versus|vs\.?|"
    r"between|across|depends on|impact of|influence|map|network|who reports|"
    r"org chart|linked)\b",
    re.I,
)
_MULTIHOP = re.compile(
    r"\b(and then|step by step|first.*then|both.*and|as well as|"
    r"after that|trace|walk me through|end to end|reconcile|cross-?reference)\b",
    re.I,
)
_FACTUAL = re.compile(
    r"^\s*(what|when|where|which|who|how much|how many|is|are|does|do|"
    r"define|list)\b",
    re.I,
)


class HeuristicRouter(QueryRouter):
    def route(self, query: str) -> RAGArchitecture:
        q = query.strip()
        # Multi-hop signals dominate: an agentic loop can absorb the others.
        if _MULTIHOP.search(q) or q.count("?") > 1:
            return RAGArchitecture.AGENTIC_LOOP
        if _RELATIONSHIP.search(q):
            return RAGArchitecture.GRAPH_RAG
        if _FACTUAL.search(q) or len(q.split()) <= 12:
            return RAGArchitecture.ADVANCED_HYBRID
        # Long, unstructured question with no clear single fact -> reason it out.
        return RAGArchitecture.AGENTIC_LOOP

"""Hybrid retrieval finds relevant content regardless of permissions."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.retrieval.fusion import reciprocal_rank_fusion
from rag_engine.schemas import EnrichedChunk, ScoredChunk, SecurityContext


def _mk(cid, text):
    return ScoredChunk(
        chunk=EnrichedChunk(
            chunk_id=cid, parent_doc_id=cid, parent_title=cid, content=text,
            security=SecurityContext(allowed_roles=["PUBLIC"]),
        ),
        score=0.0,
    )


def test_rrf_merges_and_orders():
    a, b, c = _mk("a", "x"), _mk("b", "y"), _mk("c", "z")
    lexical = [a, b]      # a is #1 lexically
    dense = [b, c]        # b is #1 densely
    fused = reciprocal_rank_fusion(lexical, dense, k=60)
    ids = [s.chunk.chunk_id for s in fused]
    # b appears in both lists -> should rank first
    assert ids[0] == "b"
    assert set(ids) == {"a", "b", "c"}


def test_pricing_query_retrieves_pricing_doc(pipeline):
    hits = pipeline.retriever.retrieve("How much does the Premium subscription cost?")
    assert any(h.chunk.parent_doc_id == "prod-pricing-2026" for h in hits)


def test_exact_number_is_findable_lexically(pipeline):
    hits = pipeline.retriever.retrieve("$200/month Premium tier")
    assert any("200" in h.chunk.content for h in hits)

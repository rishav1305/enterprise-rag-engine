"""Lightweight, dependency-free RAG metrics in the spirit of RAGAS.

These reference-based metrics are deterministic so they can run as a CI gate
without an LLM judge. For production you would also run the LLM-graded RAGAS
metrics (faithfulness, answer relevancy) on a sampled slice — same gate, richer
signal.
"""

from __future__ import annotations

from ..schemas import ScoredChunk


def context_recall(retrieved_doc_ids: list[str], relevant_doc_ids: set[str]) -> float:
    """Did we retrieve the docs that actually contain the answer?"""
    if not relevant_doc_ids:
        return 1.0
    hit = len(set(retrieved_doc_ids) & relevant_doc_ids)
    return hit / len(relevant_doc_ids)


def context_precision(retrieved_doc_ids: list[str], relevant_doc_ids: set[str]) -> float:
    """Of what we retrieved, how much was on-target?"""
    if not retrieved_doc_ids:
        return 0.0
    hit = len([d for d in retrieved_doc_ids if d in relevant_doc_ids])
    return hit / len(retrieved_doc_ids)


def governance_leak_rate(blocked_doc_ids: set[str], forbidden_doc_ids: set[str]) -> float:
    """Fraction of forbidden docs that were NOT blocked (lower is better; 0 = safe)."""
    if not forbidden_doc_ids:
        return 0.0
    leaked = forbidden_doc_ids - blocked_doc_ids
    return len(leaked) / len(forbidden_doc_ids)


def admitted_doc_ids(admitted: list[ScoredChunk]) -> list[str]:
    return list(dict.fromkeys(sc.chunk.parent_doc_id for sc in admitted))

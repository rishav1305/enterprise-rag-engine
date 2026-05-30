"""Reciprocal Rank Fusion (RRF).

RRF merges two ranked lists by rank position rather than by raw score, which
sidesteps the score-scale mismatch between BM25 (unbounded) and cosine
similarity (bounded). Score for a chunk = sum over lists of 1 / (k + rank).
``k`` (default 60) damps the influence of very high ranks. This is the same
fusion used in production hybrid stacks and in Elastic's RRF implementation.
"""

from __future__ import annotations

from ..schemas import ScoredChunk


def reciprocal_rank_fusion(
    lexical: list[ScoredChunk], dense: list[ScoredChunk], k: int = 60
) -> list[ScoredChunk]:
    fused: dict[str, ScoredChunk] = {}
    contrib: dict[str, float] = {}

    def add(items: list[ScoredChunk], which: str) -> None:
        for rank, sc in enumerate(items, start=1):
            cid = sc.chunk.chunk_id
            contrib[cid] = contrib.get(cid, 0.0) + 1.0 / (k + rank)
            if cid not in fused:
                fused[cid] = ScoredChunk(chunk=sc.chunk, score=0.0)
            if which == "lex":
                fused[cid].lexical_rank = rank
            else:
                fused[cid].dense_rank = rank

    add(lexical, "lex")
    add(dense, "dense")
    for cid, score in contrib.items():
        fused[cid].score = score
    return sorted(fused.values(), key=lambda s: -s.score)

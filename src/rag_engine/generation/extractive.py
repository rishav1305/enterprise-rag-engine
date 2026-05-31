"""Deterministic extractive generator — the default.

It composes an answer from the admitted chunks only, with no model call, so
the engine's behaviour (and especially the data-leakage test) is fully
reproducible. If governance admitted nothing, it returns a graceful refusal —
never a hallucinated answer.
"""

from __future__ import annotations

import re

from ..schemas import ScoredChunk

_REFUSAL = (
    "Access Denied due to security clearances. No content you are authorised "
    "to view matched this request."
)
_SENT = re.compile(r"(?<=[.!?])\s+")


class ExtractiveGenerator:
    def generate(self, query: str, admitted: list[ScoredChunk]) -> str:
        if not admitted:
            return _REFUSAL
        q_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        picked: list[str] = []
        for sc in admitted[:3]:
            sentences = _SENT.split(sc.chunk.content.strip())
            best = max(
                sentences,
                key=lambda s: len(q_terms & set(re.findall(r"[a-z0-9]+", s.lower()))),
                default="",
            )
            if best:
                picked.append(best.strip())
        body = " ".join(dict.fromkeys(picked))  # de-dupe, keep order
        sources = ", ".join(dict.fromkeys(sc.chunk.parent_title for sc in admitted))
        return f"{body}\n\n(Grounded in: {sources})"

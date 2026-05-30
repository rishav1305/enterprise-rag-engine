"""Offline hashing embedder — the default dense encoder.

A production deployment swaps this for sentence-transformers, Voyage, or
OpenAI embeddings behind the ``Embedder`` ABC. The hashing embedder exists so
the whole pipeline runs deterministically with no model download and no GPU —
which is exactly what you want in CI and in a portfolio reviewer's terminal.

It uses the hashing trick over word + character n-grams. It will not rival a
real bi-encoder on semantics, but it is stable, fast, and dependency-free, and
it is enough to demonstrate that hybrid fusion + governance behave correctly.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np

from .base import Embedder

_TOKEN = re.compile(r"[a-z0-9]+")


def _features(text: str) -> list[str]:
    toks = _TOKEN.findall(text.lower())
    feats: list[str] = list(toks)
    feats += [f"{a}_{b}" for a, b in zip(toks, toks[1:])]          # word bigrams
    for t in toks:                                                  # char 3-grams
        feats += [t[i : i + 3] for i in range(max(0, len(t) - 2))]
    return feats


class HashingEmbedder(Embedder):
    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for feat in _features(text):
            h = int.from_bytes(hashlib.md5(feat.encode()).digest()[:8], "little")
            idx = h % self.dim
            sign = 1.0 if (h >> 63) & 1 else -1.0
            v[idx] += sign
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else v

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self._vec(t) for t in texts])

"""Per-source deterministic RNG plumbing.

A single ``SEED`` drives the whole estate, but each source derives an
*independent* RNG seeded from ``hash(SEED, source_name)``. That guarantees two
properties the reproducibility gate depends on:

1. Regenerating the estate twice under the same ``SEED`` yields byte-identical
   output (no wall-clock, no ``uuid4``, no unseeded shuffles).
2. Adding or reordering a source never shifts another source's output — each
   source's stream is keyed by its own name, not by generation order.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
from faker import Faker

from . import SEED


def _derive_seed(source_name: str, seed: int = SEED) -> int:
    """Stable 64-bit seed from (global SEED, source name).

    Uses blake2b rather than the builtin ``hash`` (which is salted per process
    via PYTHONHASHSEED and would break reproducibility across runs).
    """
    h = hashlib.blake2b(f"{seed}:{source_name}".encode("utf-8"), digest_size=8)
    return int.from_bytes(h.digest(), "big")


@dataclass(slots=True)
class SourceRng:
    """Bundle of seeded generators for one source."""

    source_name: str
    seed: int
    np: np.random.Generator
    faker: Faker

    def fixed_epoch_offset(self, days: int) -> int:
        """Deterministic day offset helper (callers add to a fixed epoch)."""
        return days


def derive_rng(source_name: str, seed: int = SEED) -> SourceRng:
    """Return a deterministic RNG bundle for ``source_name``."""
    s = _derive_seed(source_name, seed)
    rng = np.random.default_rng(s)
    fk = Faker()
    fk.seed_instance(s)  # Faker uses its own PRNG; seed it explicitly
    return SourceRng(source_name=source_name, seed=s, np=rng, faker=fk)

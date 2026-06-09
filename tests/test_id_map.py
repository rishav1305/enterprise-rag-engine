"""P0.2b — IdMap: collision-free uint64 <-> chunk-id bijection (TurboVec keys)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.retrieval.id_map import IdMap  # noqa: E402


def test_id_map_is_stable_and_bijective():
    m = IdMap()
    a = m.to_u64("chunk:hr-001")
    b = m.to_u64("chunk:hr-001")
    assert a == b and isinstance(a, int) and a >= 0  # stable within an instance
    assert m.to_chunk_id(a) == "chunk:hr-001"        # reverse
    assert m.to_u64("chunk:fin-002") != a            # distinct ids -> distinct u64


def test_id_map_uint64_bounds():
    m = IdMap()
    for i in range(1000):
        u = m.to_u64(f"chunk:{i}")
        assert 0 <= u < 2**64


def test_id_map_roundtrips_via_serialization():
    m = IdMap()
    for i in range(50):
        m.to_u64(f"chunk:{i}")
    blob = m.to_dict()
    m2 = IdMap.from_dict(blob)
    # the mapping survives a save/load (so a loaded index resolves ids)
    assert m2.to_chunk_id(m.to_u64("chunk:7")) == "chunk:7"
    assert m2.to_u64("chunk:7") == m.to_u64("chunk:7")


def test_id_map_unknown_u64_returns_none():
    m = IdMap()
    m.to_u64("chunk:a")
    assert m.to_chunk_id(999999) is None

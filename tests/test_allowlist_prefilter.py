"""P0.2b — allowlist permission PRE-filter at the vector index.

The headline of this phase: an unauthorized vector is never returned for a
session — it is excluded at the index (drop-before-search), not post-hoc. And the
allowlist derived from the catalog/governance agrees with what the post-filter
would admit (pre-filter and post-filter are consistent).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

pytest.importorskip("turbovec")

from rag_engine.governance.allowlist import authorized_chunk_ids  # noqa: E402
from rag_engine.retrieval.turbovec_index import TurboVecIndex  # noqa: E402
from rag_engine.schemas import EnrichedChunk, SecurityContext, Session  # noqa: E402


def _unit(n, dim, seed):
    rng = np.random.default_rng(seed)
    v = rng.standard_normal((n, dim)).astype("float32")
    v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
    return v


def test_unauthorized_vector_excluded_at_index():
    v = _unit(100, 64, 1)
    ids = [f"chunk:{i}" for i in range(100)]
    idx = TurboVecIndex(dim=64)
    idx.add(ids, v)
    allow = [f"chunk:{i}" for i in range(0, 100, 2)]  # only even ids authorized
    # query near an ODD id (chunk:1) — its nearest neighbours include odd ids
    hits = idx.search(v[1], k=10, allowlist_chunk_ids=allow)
    returned = {h.chunk_id for h in hits}
    assert returned <= set(allow)            # NOTHING outside the allowlist
    assert "chunk:1" not in returned         # the unauthorized nearest is excluded


def test_empty_allowlist_returns_nothing():
    v = _unit(20, 32, 2)
    ids = [f"chunk:{i}" for i in range(20)]
    idx = TurboVecIndex(dim=32)
    idx.add(ids, v)
    assert idx.search(v[0], k=5, allowlist_chunk_ids=[]) == []  # fail-closed


# ---- allowlist derivation from catalog/governance ----------------------
def _chunk(cid, cls, level, ntk):
    return EnrichedChunk(
        chunk_id=cid, parent_doc_id=cid, parent_title="t", content="x",
        security=SecurityContext(allowed_roles=ntk, clearance_level=level,
                                 sensitivity_class=cls, need_to_know_roles=ntk),
    )


def test_authorized_chunk_ids_matches_governance():
    # mixed chunks: public (B), customer-PII (D), exec-comp (F)
    chunks = [
        _chunk("chunk:pub", "B", 1, []),
        _chunk("chunk:pii", "D", 3, []),
        _chunk("chunk:comp", "F", 5, ["C_SUITE"]),
    ]
    analyst = Session(user_id="ma", roles=["MARKETING_ANALYST", "EMPLOYEE"], clearance_level=2)
    allow = authorized_chunk_ids(analyst, chunks)
    # B allowed, D masked (retrievable, redacted downstream), F denied -> excluded
    assert "chunk:pub" in allow
    assert "chunk:pii" in allow        # mask is retrievable (C1 redacts content later)
    assert "chunk:comp" not in allow   # denied -> never a candidate
    cfo = Session(user_id="cfo", roles=["C_SUITE", "FINANCE", "EMPLOYEE"], clearance_level=5)
    assert "chunk:comp" in authorized_chunk_ids(cfo, chunks)  # CFO sees exec comp


def test_prefilter_consistent_with_postfilter():
    # the ids the allowlist admits == the ids the post-filter would NOT deny
    from rag_engine.governance.access import evaluate
    chunks = [
        _chunk("chunk:b", "B", 1, []),
        _chunk("chunk:d", "D", 3, []),
        _chunk("chunk:f", "F", 5, ["C_SUITE"]),
        _chunk("chunk:e", "E", 4, ["FINANCE", "C_SUITE"]),
    ]
    fm = Session(user_id="fm", roles=["FINANCE", "FINANCE_MANAGER", "EMPLOYEE"], clearance_level=4)
    allow = set(authorized_chunk_ids(fm, chunks))
    not_denied = {c.chunk_id for c in chunks if evaluate(c, fm).decision != "deny"}
    assert allow == not_denied

"""Schema-level guarantees: roles normalise, ACLs are enforced on the model."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.schemas import EnrichedChunk, SecurityContext


def test_roles_are_uppercased_and_deduped():
    sec = SecurityContext(allowed_roles=["c_suite", "C_SUITE", " finance "])
    assert sec.allowed_roles == ["C_SUITE", "FINANCE"]


def test_public_detection():
    assert SecurityContext(allowed_roles=["PUBLIC"], clearance_level=0).is_public
    assert not SecurityContext(allowed_roles=["C_SUITE"], clearance_level=4).is_public


def test_chunk_inherits_security_and_hashes():
    sec = SecurityContext(allowed_roles=["C_SUITE"], clearance_level=4)
    chunk = EnrichedChunk(
        chunk_id="d::0", parent_doc_id="d", parent_title="Doc",
        content="secret", security=sec, contextual_anchor="From Doc.",
    )
    assert chunk.security.clearance_level == 4
    assert chunk.embedding_text.startswith("From Doc.")
    assert len(chunk.doc_hash) == 16

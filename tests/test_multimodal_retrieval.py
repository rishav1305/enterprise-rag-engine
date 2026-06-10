"""WORKER-C — cross-modal retrieval: a text query matches a non-text chunk, still
allowlist-pre-filtered.

A text query embeds into the same space as image/table captions (via the chunk's
text surface), so a text query retrieves a relevant image/table chunk. And the
allowlist pre-filter still applies — a denied non-text chunk is never a candidate.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

pytest.importorskip("turbovec")

from rag_engine.governance.allowlist import authorized_chunk_ids  # noqa: E402,E501
from rag_engine.multimodal.embed import FakeMultimodalEmbedder  # noqa: E402
from rag_engine.multimodal.payload import attach_payload  # noqa: E402
from rag_engine.retrieval.turbovec_index import TurboVecIndex  # noqa: E402
from rag_engine.schemas import EnrichedChunk, SecurityContext, Session  # noqa: E402


def _mm(chunk_id, modality, caption, cls, level, ntk):
    md = {}
    attach_payload(md, b"raw payload")
    return EnrichedChunk(
        chunk_id=chunk_id, parent_doc_id="d", parent_title="t",
        content=caption, modality=modality, metadata=md,
        security=SecurityContext(allowed_roles=ntk, clearance_level=level,
                                 sensitivity_class=cls, need_to_know_roles=ntk),
    )


def test_text_query_retrieves_image_chunk_cross_modal():
    emb = FakeMultimodalEmbedder(dim=256)
    chunks = [
        _mm("img:revenue", "image", "quarterly revenue bar chart", "B", 1, []),
        _mm("img:org", "image", "company org structure diagram", "B", 1, []),
    ]
    idx = TurboVecIndex(dim=256)
    idx.add([c.chunk_id for c in chunks], emb.embed_chunks(chunks))

    session = Session(user_id="u", roles=["EMPLOYEE"], clearance_level=2)
    allow = authorized_chunk_ids(session, chunks)
    q = emb.embed(["show me the revenue chart"])[0]
    hits = idx.search(q, k=2, allowlist_chunk_ids=allow)
    # the revenue image chunk is the top cross-modal hit for a text query
    assert hits[0].chunk_id == "img:revenue"


def test_denied_image_never_a_candidate_cross_modal():
    emb = FakeMultimodalEmbedder(dim=256)
    chunks = [
        _mm("img:secret", "image", "executive compensation figures chart",
            "F", 5, ["C_SUITE"]),               # DENY for under-cleared
        _mm("img:pub", "image", "public revenue chart", "B", 1, []),
    ]
    idx = TurboVecIndex(dim=256)
    idx.add([c.chunk_id for c in chunks], emb.embed_chunks(chunks))

    under = Session(user_id="emp", roles=["EMPLOYEE"], clearance_level=2)
    allow = authorized_chunk_ids(under, chunks)   # img:secret excluded
    # query SEMANTICALLY closest to the secret image
    q = emb.embed(["executive compensation figures"])[0]
    hits = idx.search(q, k=5, allowlist_chunk_ids=allow)
    ids = {h.chunk_id for h in hits}
    assert "img:secret" not in ids                # denied image never a candidate
    assert ids <= {"img:pub"}                      # only the allowed one


def test_index_embeds_text_surface_not_raw_payload():
    """The embedding IS the caption embedding — NOT the raw bytes. Coupled to the
    text surface so embedding the payload instead is caught.

    BITES: mutate embed_chunks to embed repr(get_payload(...)) -> the chunk vector no
    longer equals the caption vector -> these assertions fail.
    """
    import numpy as np
    emb = FakeMultimodalEmbedder(dim=64)
    chunk = _mm("img:1", "image", "quarterly revenue chart caption", "B", 1, [])
    # the chunk's embedding equals the embedding of its TEXT surface (the caption)
    assert np.allclose(emb.embed_chunks([chunk]), emb.embed([chunk.embedding_text]))

    # and two chunks with the SAME caption but DIFFERENT raw payloads embed
    # IDENTICALLY (proving the payload is not in the embedding at all).
    a = _mm("a", "image", "identical caption text", "B", 1, [])
    b = _mm("b", "image", "identical caption text", "B", 1, [])
    a.metadata["mm_payload"] = b"PAYLOAD_AAAA"
    b.metadata["mm_payload"] = b"PAYLOAD_BBBB_totally_different"
    assert np.allclose(emb.embed_chunks([a]), emb.embed_chunks([b]))

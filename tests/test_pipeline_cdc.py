"""P0.11a W7 — CdcProcessor wired into RAGPipeline (governance propagation, live).

pipeline.apply_change drives a CdcProcessor over the in-memory chunk set + the cache:
a RECLASSIFY-up via the pipeline -> the under-cleared session's NEXT query is denied
(allowlist re-derives from the new classification) AND the stale permissive cache
entry is invalidated. embedder_version is configurable + read by the query path.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.cdc.events import ChangeOp, ChunkChangeEvent  # noqa: E402
from rag_engine.config import EngineConfig  # noqa: E402
from rag_engine.governance import access  # noqa: E402
from rag_engine.pipeline import RAGPipeline  # noqa: E402
from rag_engine.schemas import Document, SecurityContext, Session  # noqa: E402

SECRET = "CDC_PIPELINE_EXEC_SECRET"


def _pipeline_with_b_chunk():
    pipe = RAGPipeline()
    doc = Document(doc_id="doc1", title="Project Notes",
                   content=f"Project notes that mention {SECRET}.",
                   security=SecurityContext(allowed_roles=["PUBLIC"], clearance_level=0,
                                            sensitivity_class="B", need_to_know_roles=[]))
    pipe.index_documents([doc])
    return pipe


def _chunk_id(pipe):
    return pipe._chunks[0].chunk_id


def test_embedder_version_configurable():
    assert EngineConfig().embedder_version == "hashing-v1"


def test_reclassify_up_denies_under_cleared_next_query():
    pipe = _pipeline_with_b_chunk()
    under = Session(user_id="emp", roles=["EMPLOYEE"], clearance_level=2)
    cid = _chunk_id(pipe)

    # BEFORE: class-B chunk -> the under-cleared session is authorized.
    chunk_before = next(c for c in pipe._chunks if c.chunk_id == cid)
    assert access.evaluate(chunk_before, under).decision != "deny"

    # RECLASSIFY UP B -> F via the pipeline CDC seam.
    applied = pipe.apply_change(ChunkChangeEvent(
        ChangeOp.RECLASSIFY, cid, 2,
        {"asset_id": "doc1", "cls": "F", "level": 5,
         "allowed_roles": ["C_SUITE"], "need_to_know": ["C_SUITE"],
         "text": "Project notes (now restricted)."}))
    assert applied is True

    # AFTER: the chunk is now class-F -> the under-cleared session is DENIED.
    chunk_after = next(c for c in pipe._chunks if c.chunk_id == cid)
    assert chunk_after.security.sensitivity_class == "F"
    assert access.evaluate(chunk_after, under).decision == "deny"


def test_reclassify_invalidates_stale_cache():
    pipe = _pipeline_with_b_chunk()           # cache enabled by default
    cfo = Session(user_id="cfo", roles=["C_SUITE"], clearance_level=5)
    cid = _chunk_id(pipe)
    # cfo queries -> a result referencing the chunk is cached under the cfo scope.
    pipe.query("project notes", cfo)
    # RECLASSIFY -> the chunk's cache entries are invalidated.
    pipe.apply_change(ChunkChangeEvent(
        ChangeOp.RECLASSIFY, cid, 2,
        {"asset_id": "doc1", "cls": "F", "level": 5,
         "allowed_roles": ["C_SUITE"], "text": "now restricted"}))
    # the chunk is no longer in any cache entry (invalidated) — re-query recomputes.
    # (the cache is in-process; assert no entry references the chunk id.)
    assert all(cid not in e.chunk_ids for e in pipe.cache._entries.values())


def test_delete_via_cdc_removes_chunk():
    pipe = _pipeline_with_b_chunk()
    cid = _chunk_id(pipe)
    pipe.apply_change(ChunkChangeEvent(ChangeOp.DELETE, cid, 2))
    assert all(c.chunk_id != cid for c in pipe._chunks)


def test_stale_event_dropped():
    pipe = _pipeline_with_b_chunk()
    cid = _chunk_id(pipe)
    assert pipe.apply_change(ChunkChangeEvent(ChangeOp.UPDATE, cid, 5,
                                              {"cls": "B", "level": 1, "text": "new"})) is True
    # a lower-version event is dropped (ordering)
    assert pipe.apply_change(ChunkChangeEvent(ChangeOp.UPDATE, cid, 3,
                                              {"cls": "B", "level": 1, "text": "stale"})) is False

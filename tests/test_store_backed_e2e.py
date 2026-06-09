"""P0.2d HEADLINE — STORE-BACKED C1-over-vector E2E (production-wired governance).

The store-backed twin of ``tests/test_c1_over_vector_e2e.py``. SAME guarantees,
but the ``ChunkSource`` is a real ``SurrealChunkSource`` over a live ``SurrealStore``
instead of an in-memory ``_DictSource`` — so this proves governance enforcement
against the PRODUCTION store wiring (allowlist pre-filter derived from STORE ACLs +
hydration from STORE rows + mandatory rerank + L5 C1 masking):

  * a class-D chunk with raw PII -> ``[REDACTED]`` in BOTH answer and citations,
    with raw email/phone/SSN never present, MASKED-not-dropped;
  * a class-F (L5) chunk in the same store/index is NEVER in an under-cleared
    analyst's candidate set (allowlist drop-before-search, asserted BEFORE the
    L5 post-filter so a bypassed pre-filter FAILS this test); and
  * the CFO (L5, C_SUITE) DOES get that same class-F chunk through the same path.

"live" -> "production-wired": the in-memory double is gone; every chunk and every
ACL is read back out of SurrealDB. Chunks are INSERTED directly via
``store.upsert_chunk(...)`` in the EXACT row shape ``seeds.targets.turbovec_target
.build_index`` writes (asset_id / cls / level / text / vec), and their vectors are
added to a ``TurboVecIndex`` keyed by the SAME bare chunk ids the store projects.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("turbovec")
pytest.importorskip("surrealdb")

from rag_engine import RAGPipeline, Session  # noqa: E402
from rag_engine.config import EngineConfig  # noqa: E402
from rag_engine.retrieval.embedders import HashingEmbedder  # noqa: E402
from rag_engine.retrieval.rerank import LexicalOverlapReranker  # noqa: E402
from rag_engine.retrieval.turbovec_index import TurboVecIndex  # noqa: E402
from rag_engine.retrieval.turbovec_retriever import TurboVecRetriever  # noqa: E402
from rag_engine.store.chunk_source import SurrealChunkSource  # noqa: E402
from rag_engine.store.surreal import SurrealStore  # noqa: E402

# Real canaries (mirror the in-memory E2E's _RAW_PII / _SECRETS exactly).
_RAW_PII = "Customer jane.doe@example.com phone 555-867-5309 SSN 123-45-6789 contact record"
_SECRETS = ("jane.doe@example.com", "555-867-5309", "123-45-6789")

# Bare chunk keys (the store strips the `chunk:` prefix; SurrealChunkSource and the
# index both speak bare ids, so assertions use these — not `chunk:execcomp`).
_ID_CUST = "store_e2e-cust"        # class-D customer PII   -> MASK for an L2 analyst
_ID_EXEC = "store_e2e-execcomp"    # class-F exec comp (L5) -> DENY for analyst, ALLOW CFO
_ID_PUB = "store_e2e-pub"          # class-B public         -> ALLOW raw

# (chunk_id, text, asset_id, cls, level) — the rows we INSERT into the live store.
_ROWS = [
    (_ID_CUST, _RAW_PII, "store_e2e_customers", "D", 3),
    (_ID_EXEC, "exec comp ceo salary 480000 contact need_to_know C_SUITE",
     "store_e2e_finance", "F", 5),
    (_ID_PUB, "remote work stipend 500 dollars contact", "store_e2e_handbook", "B", 1),
]


def _seed_store_and_index(surreal_local, db: str, dim: int):
    """Insert the 3 governance test chunks into a LIVE store + build the matching
    TurboVec index, in the SAME row shape as ``turbovec_target.build_index``.

    Returns (store, SurrealChunkSource, TurboVecIndex). Caller closes the store.
    """
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db=db,
                      user="root", password="root")
    st.connect()
    st.apply_schema(vector_dim=dim)

    emb = HashingEmbedder(dim=dim)
    texts = [r[1] for r in _ROWS]
    # Mirror build_index: embed the stored text, then L2-normalise the matrix.
    vectors = emb.embed(texts).astype("float32")
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9

    chunk_ids = [r[0] for r in _ROWS]
    idx = TurboVecIndex(dim=dim)
    idx.add(chunk_ids, vectors)

    # vectors-by-id + governance footprint INTO the live store (per S2 row shape).
    for (cid, text, asset_id, cls, level), vec in zip(_ROWS, vectors):
        st.upsert_chunk({
            "chunk_id": cid,
            "asset_id": asset_id,
            "cls": cls,
            "level": level,
            "text": text,
            "vec": vec.tolist(),
        })
    # Confirm the live store actually round-trips the governance footprint we rely
    # on (so a broken insert fails loudly here, not as a confusing E2E miss).
    assert st.count_chunks() == len(_ROWS)
    return st, SurrealChunkSource(st), idx


@pytest.fixture
def store_pipeline_with_pii(surreal_local):
    """Live-store twin of the in-memory ``vector_pipeline_with_pii`` fixture.

    Wires ``RAGPipeline(vector_retriever=TurboVecRetriever(... SurrealChunkSource))``
    so the vector path hydrates + derives its allowlist from the REAL store. Unique
    db= keeps the run isolated + deterministic.
    """
    cfg = EngineConfig()
    emb = HashingEmbedder(dim=cfg.embedding_dim)
    st, source, idx = _seed_store_and_index(
        surreal_local, db="store_e2e_c1", dim=cfg.embedding_dim
    )
    try:
        retriever = TurboVecRetriever(idx, emb, source, LexicalOverlapReranker(), cfg)
        pipe = RAGPipeline(config=cfg, vector_retriever=retriever)
        analyst = Session(user_id="ma", roles=["MARKETING_ANALYST", "EMPLOYEE"],
                          clearance_level=2)
        # expose the retriever so the E2E can assert on the CANDIDATE SET (pre-post-filter)
        yield pipe, analyst, retriever
    finally:
        st.close()


def test_class_D_pii_redacted_via_store_backed_path(store_pipeline_with_pii):
    """1. class-D via the LIVE STORE path -> raw PII absent in answer + every quote."""
    pipe, analyst, _ = store_pipeline_with_pii
    resp = pipe.query("show me the customer contact record", analyst)
    for secret in _SECRETS:
        assert secret not in resp.answer, f"LEAK in answer: {secret}"
        for c in resp.citations:
            assert secret not in c.quote, f"LEAK in citation: {secret}"


def test_class_D_chunk_is_masked_not_dropped_via_store(store_pipeline_with_pii):
    """2. class-D is MASKED-not-dropped: the chunk is retrieved + cited (from the
    store), and its quote carries the redaction token (not blacked-out / dropped)."""
    pipe, analyst, _ = store_pipeline_with_pii
    resp = pipe.query("customer contact record", analyst)
    cited = {c.parent_doc_id for c in resp.citations}
    # the class-D chunk's parent asset IS cited (admitted, not dropped)
    assert "store_e2e_customers" in cited
    quotes = " ".join(c.quote for c in resp.citations)
    assert "[REDACTED]" in quotes or "[RESTRICTED]" in quotes


def test_class_F_L5_excluded_at_index_before_post_filter_store(store_pipeline_with_pii):
    """3. HARDENED pre-filter isolation: the class-F/L5 chunk is NEVER in the
    analyst's candidate set — asserted on ``retrieve_for_session`` output BEFORE the
    L5 SecurityFilter, with the allowlist derived from STORE ACLs. FAILS if the
    pre-filter is bypassed (a post-filter alone would mask the chunk, hiding the leak)."""
    pipe, analyst, retriever = store_pipeline_with_pii
    candidates = retriever.retrieve_for_session("exec comp ceo salary contact", analyst)
    candidate_ids = {sc.chunk.chunk_id for sc in candidates}
    assert _ID_EXEC not in candidate_ids, (
        "PRE-FILTER BYPASS: the L5 chunk reached the analyst's candidate set via the "
        "live store path — the STORE-ACL allowlist drop-before-search is not enforcing."
    )
    # ...and end-to-end the secret never surfaces.
    resp = pipe.query("exec comp ceo salary contact", analyst)
    assert "store_e2e_finance" not in {c.parent_doc_id for c in resp.citations}
    assert "480000" not in resp.answer


def test_cfo_does_get_exec_comp_via_store_backed_path(store_pipeline_with_pii):
    """4. CFO control: the SAME store/index returns the class-F chunk to a CFO
    (L5, C_SUITE) — the pre-filter admits it because the STORE ACL grants need-to-know."""
    pipe, _, retriever = store_pipeline_with_pii
    cfo = Session(user_id="cfo", roles=["C_SUITE", "FINANCE", "EMPLOYEE"],
                  clearance_level=5)
    candidate_ids = {sc.chunk.chunk_id
                     for sc in retriever.retrieve_for_session("exec comp ceo salary contact", cfo)}
    assert _ID_EXEC in candidate_ids
    resp = pipe.query("exec comp ceo salary contact", cfo)
    assert "store_e2e_finance" in {c.parent_doc_id for c in resp.citations}
    assert "480000" in resp.answer


def test_mixed_class_response_B_raw_and_D_masked_store_backed(store_pipeline_with_pii):
    """5. Multi-class in ONE store-backed response: class-B stays RAW and class-D
    is MASKED ([REDACTED]) in the same citation set — proving per-chunk governance
    (not all-or-nothing) over the real store path. (Class-F is dropped, covered
    elsewhere.)"""
    pipe, analyst, _ = store_pipeline_with_pii
    resp = pipe.query("customer contact record stipend", analyst)
    cited = {c.parent_doc_id for c in resp.citations}
    quotes = " ".join(c.quote for c in resp.citations)
    # B: public chunk admitted RAW (its handbook content survives)
    assert "store_e2e_handbook" in cited
    assert "500" in quotes or "stipend" in quotes.lower()
    # D: customer-PII admitted but MASKED — redaction token, raw PII absent
    assert "store_e2e_customers" in cited
    assert "[REDACTED]" in quotes
    for secret in _SECRETS:
        assert secret not in quotes and secret not in resp.answer


def test_store_drift_id_in_index_absent_from_store_is_dropped(surreal_local):
    """6. RESILIENT store drift: an id in the TurboVec index but ABSENT from the
    store (get_chunk -> None) is silently dropped end-to-end — non-crashing result,
    the present chunk still returned. (turbovec_retriever's `if chunk is not None`.)"""
    cfg = EngineConfig()
    emb = HashingEmbedder(dim=cfg.embedding_dim)
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db="store_e2e_drift",
                      user="root", password="root")
    st.connect()
    st.apply_schema(vector_dim=cfg.embedding_dim)

    present_id, ghost_id = "store_drift-present", "store_drift-ghost"
    texts = ["public stipend record contact", "ghost record contact"]
    vecs = emb.embed(texts).astype("float32")
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    idx = TurboVecIndex(dim=cfg.embedding_dim)
    idx.add([present_id, ghost_id], vecs)  # BOTH ids in the index...

    # ...but ONLY the present chunk is upserted into the store (ghost is missing).
    st.upsert_chunk({"chunk_id": present_id, "asset_id": "store_drift", "cls": "B",
                     "level": 1, "text": texts[0], "vec": vecs[0].tolist()})
    try:
        source = SurrealChunkSource(st)
        retriever = TurboVecRetriever(idx, emb, source, LexicalOverlapReranker(), cfg)
        pipe = RAGPipeline(config=cfg, vector_retriever=retriever)
        emp = Session(user_id="e", roles=["EMPLOYEE"], clearance_level=1)
        # ghost is also absent from the allowlist (all_chunk_security skips it) AND
        # would hydrate to None — defense in depth. The query must not crash.
        resp = pipe.query("contact record", emp)
        cited = {c.parent_doc_id for c in resp.citations}
        assert ghost_id not in {sc.chunk.chunk_id
                                for sc in retriever.retrieve_for_session("contact record", emp)}
        # the present chunk still comes through (non-empty, non-crashing)
        assert "store_drift" in cited
    finally:
        st.close()

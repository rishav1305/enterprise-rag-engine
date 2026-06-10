"""WORKER-C — re-embedding preserves SecurityContext + bumps version.

A version-bump re-embed must NOT drop/alter a chunk's ACL: cls, level, allowed_roles,
need_to_know are byte-identical after, and the governance decision is unchanged. The
new embedding vector + embedder_version are written; the OLD-version cache is
invalidated (ties to invalidate_version).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.cdc.reembed import ReEmbedder  # noqa: E402
from rag_engine.governance import access  # noqa: E402
from rag_engine.retrieval.embedders import HashingEmbedder  # noqa: E402
from rag_engine.store.chunk_source import SurrealChunkSource  # noqa: E402
from rag_engine.schemas import Session  # noqa: E402


def _store(surreal_local):
    from rag_engine.store.surreal import SurrealStore
    st = SurrealStore(dsn=surreal_local["dsn"], ns=surreal_local["ns"],
                      db=surreal_local["db"], user=surreal_local["user"],
                      password=surreal_local["pass"])
    st.connect()
    st.apply_schema(vector_dim=8)   # small dim so the HNSW index matches our test vecs
    return st


class _SpyCache:
    def __init__(self):
        self.invalidated_versions: list[str] = []

    def invalidate_version(self, v):
        self.invalidated_versions.append(v)


def test_reembed_preserves_security_context(surreal_local):
    st = _store(surreal_local)
    # a class-F exec-comp chunk with a non-trivial ACL
    st.upsert_chunk({"chunk_id": "doc:1", "asset_id": "a1", "cls": "F", "level": 5,
                     "text": "exec compensation details", "vec": [0.0] * 8,
                     "embedder_version": "ra1"})
    before = st.get_chunk_row("doc:1")
    cls_before, level_before = before["cls"], before["level"]

    cache = _SpyCache()
    re = ReEmbedder(store=st, embedder=HashingEmbedder(dim=8),
                    new_version="ra2", cache=cache)
    re.reembed_all(old_version="ra1")

    after = st.get_chunk_row("doc:1")
    # ACL fields byte-identical
    assert after["cls"] == cls_before == "F"
    assert after["level"] == level_before == 5
    # version bumped + a (new) vector present
    assert after["embedder_version"] == "ra2"
    assert after["vec"] is not None
    # the old-version cache was invalidated (ties to invalidate_version)
    assert "ra1" in cache.invalidated_versions


def test_reembed_does_not_change_governance_decision(surreal_local):
    st = _store(surreal_local)
    st.upsert_chunk({"chunk_id": "doc:2", "asset_id": "a1", "cls": "D", "level": 3,
                     "text": "customer pii ssn", "vec": [0.0] * 8,
                     "embedder_version": "rb1"})
    source = SurrealChunkSource(st)
    s = Session(user_id="emp", roles=["EMPLOYEE"], clearance_level=2)

    chunk_before = source.get_chunk("doc:2")
    dec_before = access.evaluate(chunk_before, s).decision

    ReEmbedder(st, HashingEmbedder(dim=8), "rb2", _SpyCache()).reembed_all("rb1")

    chunk_after = source.get_chunk("doc:2")
    dec_after = access.evaluate(chunk_after, s).decision
    assert dec_after == dec_before == "mask"   # class-D @ L2 stays mask, unchanged


def test_reembed_is_resumable_only_touches_old_version(surreal_local):
    st = _store(surreal_local)
    st.upsert_chunk({"chunk_id": "old", "asset_id": "a1", "cls": "B", "level": 1,
                     "text": "old version chunk", "vec": [0.0] * 8,
                     "embedder_version": "rc1"})
    st.upsert_chunk({"chunk_id": "new", "asset_id": "a1", "cls": "B", "level": 1,
                     "text": "already new chunk", "vec": [1.0] * 8,
                     "embedder_version": "rc2"})
    n = ReEmbedder(st, HashingEmbedder(dim=8), "rc2", _SpyCache()).reembed_all("rc1")
    assert n == 1                                   # only the rc1 chunk re-embedded
    assert st.get_chunk_row("new")["vec"] == [1.0] * 8  # the v2 chunk untouched

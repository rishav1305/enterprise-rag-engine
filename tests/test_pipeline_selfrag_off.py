"""P0.11a FIX4 — selfrag-OFF answer path governs via the pipeline's own L5 filter.

With selfrag ON (default) the answer comes from the loop (which self-redacts). With
selfrag OFF, the answer comes from generate(question, admitted) where `admitted` is
the pipeline's own SecurityFilter.apply output — so the L5 filter MUST govern the
answer directly. Both answer-paths must be proven to withhold deny/mask content.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.config import EngineConfig  # noqa: E402
from rag_engine.pipeline import RAGPipeline  # noqa: E402
from rag_engine.schemas import Document, SecurityContext, Session  # noqa: E402

DENY_SECRET = "OFF_PATH_EXEC_SECRET"
MASK_SECRET = "OFF_PATH_PII_SECRET"


def _pipeline_selfrag_off():
    import os
    os.environ["RAG_SELFRAG_ENABLED"] = "0"
    try:
        cfg = EngineConfig()
    finally:
        del os.environ["RAG_SELFRAG_ENABLED"]
    assert cfg.selfrag_enabled is False
    pipe = RAGPipeline(config=cfg)
    docs = [
        Document(doc_id="comp", title="Exec Comp",
                 content=f"Executive compensation board figure {DENY_SECRET}.",
                 security=SecurityContext(allowed_roles=["C_SUITE"], clearance_level=5,
                                          sensitivity_class="F",
                                          need_to_know_roles=["C_SUITE"])),
        Document(doc_id="pii", title="Customer",
                 content=f"Customer record SSN {MASK_SECRET} on file.",
                 security=SecurityContext(allowed_roles=[], clearance_level=1,
                                          sensitivity_class="D", need_to_know_roles=[])),
    ]
    pipe.index_documents(docs)
    return pipe


def test_selfrag_off_pipeline_is_configured():
    pipe = _pipeline_selfrag_off()
    assert pipe.selfrag_enabled is False


def test_selfrag_off_answer_withholds_deny_and_mask():
    pipe = _pipeline_selfrag_off()
    intern = Session(user_id="intern", roles=["INTERN"], clearance_level=1)
    for q in ["executive compensation", "customer record"]:
        resp = pipe.query(q, intern)
        assert DENY_SECRET not in resp.answer, "selfrag-OFF: DENY content leaked to answer"
        assert MASK_SECRET not in resp.answer, "selfrag-OFF: MASK content leaked to answer"

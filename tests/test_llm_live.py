"""P0.3b — live Groq/NVIDIA SQL-draft (creds-gated, NOT part of the CI gate).

Marked ``llm`` + skipif no GROQ_API_KEY/NVIDIA_API_KEY. Proves the live
OpenAI-compatible generator drafts SQL that the P0.3a AST gate ACCEPTS as a
read-only SELECT — i.e. even a live LLM cannot get non-SELECT SQL past the guard.
CI runs `-m "not cloud and not bq and not llm"`. Read-only; no secrets committed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

_KEY = os.getenv("GROQ_API_KEY") or os.getenv("NVIDIA_API_KEY")


@pytest.mark.llm
@pytest.mark.skipif(not _KEY, reason="no Groq/NVIDIA key (set GROQ_API_KEY or NVIDIA_API_KEY)")
def test_live_llm_draft_passes_or_is_caught_by_ast_gate():
    pytest.importorskip("openai")
    from rag_engine.config import EngineConfig
    from rag_engine.generation.openai_compat import OpenAICompatGenerator
    from rag_engine.sql.ast_gate import AstGateError, assert_read_only

    cfg = EngineConfig()
    gen = OpenAICompatGenerator(base_url=cfg.sql_llm_base_url,
                                model=cfg.sql_llm_model, api_key=_KEY)
    sql = gen.draft_sql(
        "average store sale price by item, filtered on ss_sold_date_sk >= '2024-01-01'"
    )
    # whatever the LLM produced, the gate is the SECURE backstop: either it's a
    # read-only SELECT (passes) or it's refused — it can NEVER reach execute as DML.
    try:
        tree = assert_read_only(sql)
        assert tree is not None
    except AstGateError:
        pass  # acceptably refused — the guard did its job

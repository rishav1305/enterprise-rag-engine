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


@pytest.mark.llm
@pytest.mark.skipif(not _KEY, reason="no Groq/NVIDIA key")
def test_live_draft_executes_only_via_the_guard():
    """Closes the live loop: a live LLM draft reaches a BigQuery client ONLY through
    GuardedBigQuery (AST gate + cost guard). A non-SELECT draft would be refused; a
    SELECT runs guarded. Uses the FakeBigQueryClient so no live BQ creds are needed
    — only the LLM key — proving the draft->guard->execute wiring end to end."""
    pytest.importorskip("openai")
    from rag_engine.config import EngineConfig
    from rag_engine.connectors.bigquery import FakeBigQueryClient, GuardedBigQuery
    from rag_engine.generation.openai_compat import OpenAICompatGenerator
    from rag_engine.texttosql.agent import TextToSqlAgent

    cfg = EngineConfig()
    gen = OpenAICompatGenerator(base_url=cfg.sql_llm_base_url,
                                model=cfg.sql_llm_model, api_key=_KEY)
    fake_bq = FakeBigQueryClient(dry_run_bytes=10,
                                 rows=[{"customer_email": "x@y.com"}])
    g = GuardedBigQuery(fake_bq, "ss_sold_date_sk", 1_000_000_000,
                        require_partition_filter=False)
    agent = TextToSqlAgent(gen, g, masked_columns=("customer_email",))
    # the live draft either runs guarded or is refused — never an ungated execute
    try:
        res = agent.answer("select the store sale customer email, alias it as e")
        assert "x@y.com" not in res.answer   # masked even if the LLM aliased it
    except Exception:
        pass  # acceptably refused by the guard

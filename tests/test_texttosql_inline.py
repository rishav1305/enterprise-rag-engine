"""P0.3b Batch-A inline tests (result masking + agent + router). WORKER-A/B extend."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_mask_rows_redacts_masked_columns():
    from rag_engine.catalog.asset import ColumnPolicy
    from rag_engine.texttosql.result_masking import mask_rows
    cols = (ColumnPolicy(name="fare", pii=False, masked=False),
            ColumnPolicy(name="customer_email", pii=True, masked=True,
                         mask_reason="PII_MASK"))
    rows = [{"fare": 12.5, "customer_email": "jane@example.com"}]
    masked = mask_rows(rows, cols, mask=True)
    assert masked[0]["fare"] == 12.5
    assert masked[0]["customer_email"] == "[REDACTED]"
    assert "jane@example.com" not in str(masked)


def test_mask_rows_passthrough_when_not_masking():
    from rag_engine.catalog.asset import ColumnPolicy
    from rag_engine.texttosql.result_masking import mask_rows
    cols = (ColumnPolicy(name="customer_email", pii=True, masked=True,
                         mask_reason="PII_MASK"),)
    rows = [{"customer_email": "jane@example.com"}]
    out = mask_rows(rows, cols, mask=False)   # cleared role -> raw
    assert out[0]["customer_email"] == "jane@example.com"


def test_agent_runs_guarded_sql_and_masks_results():
    from rag_engine.connectors.bigquery import FakeBigQueryClient, GuardedBigQuery
    from rag_engine.generation.openai_compat import FakeSqlGenerator
    from rag_engine.texttosql.agent import TextToSqlAgent
    gen = FakeSqlGenerator({"avg fare": "SELECT fare, customer_email FROM s "
                            "WHERE ss_sold_date_sk >= '2024-01-01'"})
    fake_bq = FakeBigQueryClient(dry_run_bytes=10,
                                 rows=[{"fare": 12.5,
                                        "customer_email": "jane@example.com"}])
    g = GuardedBigQuery(fake_bq, "ss_sold_date_sk", 1_000_000_000)
    agent = TextToSqlAgent(gen, g, masked_columns=("customer_email",))
    result = agent.answer("avg fare", mask=True)
    assert "jane@example.com" not in result.answer
    assert "[REDACTED]" in str(result.rows)


def test_semantic_router_is_deterministic_and_routes():
    from rag_engine.routing.semantic_router import SemanticRouter
    from rag_engine.schemas import RAGArchitecture
    r = SemanticRouter()
    a = r.route("error code ERR-DB-0042")
    b = r.route("error code ERR-DB-0042")
    assert a == b                                   # deterministic
    assert isinstance(a, RAGArchitecture)


def test_config_router_and_sql_generator_backends():
    from rag_engine.config import EngineConfig
    cfg = EngineConfig()
    assert cfg.router_backend in ("heuristic", "semantic")
    assert cfg.sql_generator in ("fake", "groq", "nvidia")

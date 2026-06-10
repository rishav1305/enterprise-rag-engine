"""P0.11a W5 — text-to-SQL + GuardedBigQuery wired into RAGPipeline.

Through pipeline.query_warehouse: the mask flag is DERIVED from governance over the
warehouse asset for the session (not a literal), the ColumnPolicy comes from the
catalog asset, and result rows are masked BY AST SOURCE before the model. An
under-cleared session sees [REDACTED]; a cleared session sees the raw value.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.catalog.asset import CatalogAsset, ColumnPolicy  # noqa: E402
from rag_engine.connectors.bigquery import FakeBigQueryClient, GuardedBigQuery  # noqa: E402
from rag_engine.generation.openai_compat import FakeSqlGenerator  # noqa: E402
from rag_engine.pipeline import RAGPipeline  # noqa: E402
from rag_engine.schemas import SecurityContext, Session  # noqa: E402
from rag_engine.texttosql.agent import TextToSqlAgent  # noqa: E402

_RAW_EMAIL = "jane.doe@example.com"
_PART = "ss_sold_date_sk"


def _asset():
    # a class-D (customer PII) warehouse asset; customer_email is a masked column.
    return CatalogAsset(
        asset_id="warehouse_customers", vertical="retail", retrieval_mode="text_to_sql",
        sensitivity_class="D",
        security=SecurityContext(allowed_roles=[], clearance_level=3,
                                 sensitivity_class="D", need_to_know_roles=[]),
        columns=(ColumnPolicy(name="customer_email", pii=True, masked=True,
                              mask_reason="PII_MASK"),),
    )


def _agent(rows):
    gen = FakeSqlGenerator({
        "customer contacts": f"SELECT customer_email FROM s WHERE {_PART} >= '2024-01-01'"
    })
    g = GuardedBigQuery(FakeBigQueryClient(dry_run_bytes=10, rows=rows),
                        _PART, 1_000_000_000)
    return TextToSqlAgent(gen, g)   # columns sourced from the asset by the pipeline


def test_under_cleared_session_gets_redacted_warehouse_result():
    pipe = RAGPipeline()
    agent = _agent(rows=[{"customer_email": _RAW_EMAIL}])
    # L2 employee over a class-D asset -> mask
    under = Session(user_id="emp", roles=["EMPLOYEE"], clearance_level=2)
    res = pipe.query_warehouse("customer contacts", under, agent, _asset())
    assert _RAW_EMAIL not in res.answer, "WAREHOUSE LEAK: raw PII in the answer"
    assert _RAW_EMAIL not in str(res.rows)
    assert any(r["customer_email"] == "[REDACTED]" for r in res.rows)
    assert res.masked is True


def test_cleared_session_gets_raw_warehouse_result():
    pipe = RAGPipeline()
    agent = _agent(rows=[{"customer_email": _RAW_EMAIL}])
    # L4+ cleared over class-D -> allow (raw)
    cleared = Session(user_id="dir", roles=["DIRECTOR"], clearance_level=4)
    res = pipe.query_warehouse("customer contacts", cleared, agent, _asset())
    assert res.masked is False
    assert any(r["customer_email"] == _RAW_EMAIL for r in res.rows)


def _denied_asset():
    # a class-F (exec-comp, NTK C_SUITE, L5) warehouse asset with a NON-masked column
    # (salary). An under-cleared session gets DENY -> must get NO rows (the column is
    # not flagged masked, so mask-only redaction would leak it raw).
    return CatalogAsset(
        asset_id="warehouse_payroll", vertical="hr", retrieval_mode="text_to_sql",
        sensitivity_class="F",
        security=SecurityContext(allowed_roles=["C_SUITE"], clearance_level=5,
                                 sensitivity_class="F", need_to_know_roles=["C_SUITE"]),
        columns=(ColumnPolicy(name="salary", pii=False, masked=False),),  # NOT flagged
    )


def _salary_agent():
    gen = FakeSqlGenerator({"payroll": f"SELECT salary FROM s WHERE {_PART} >= '2024-01-01'"})
    g = GuardedBigQuery(FakeBigQueryClient(dry_run_bytes=10, rows=[{"salary": 999999}]),
                        _PART, 1_000_000_000)
    return TextToSqlAgent(gen, g)


def test_denied_session_gets_no_warehouse_rows():
    """A DENY decision must short-circuit BEFORE running SQL — the text path drops
    deny before the model, the warehouse path must too. mask-only column redaction
    would leak a non-flagged column (salary) raw to a denied session.

    BITES: collapse deny->mask (run the query) -> the raw salary surfaces -> fails.
    """
    pipe = RAGPipeline()
    intern = Session(user_id="intern", roles=["INTERN"], clearance_level=1)
    res = pipe.query_warehouse("payroll", intern, _salary_agent(), _denied_asset())
    assert res.rows == [], "WAREHOUSE DENY LEAK: denied session got rows"
    assert "999999" not in str(res.rows) and "999999" not in res.answer
    assert res.access_denied is True


def test_mask_flag_is_governance_derived_not_literal():
    # the SAME query/asset yields different mask outcomes purely from the session's
    # clearance -> the flag is session-governance-driven, not hardcoded.
    pipe = RAGPipeline()
    asset = _asset()
    under = Session(user_id="a", roles=["EMPLOYEE"], clearance_level=2)
    cleared = Session(user_id="b", roles=["DIRECTOR"], clearance_level=4)
    r_under = pipe.query_warehouse("customer contacts",
                                   under, _agent([{"customer_email": _RAW_EMAIL}]), asset)
    r_cleared = pipe.query_warehouse("customer contacts",
                                     cleared, _agent([{"customer_email": _RAW_EMAIL}]), asset)
    assert r_under.masked is True and r_cleared.masked is False

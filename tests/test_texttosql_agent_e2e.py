"""P0.3b HEADLINE — masked SQL result rows never reach the model (hard gate).

A warehouse query whose result has a masked column (customer_email) must, for an
under-cleared (masked) session: be `[REDACTED]` in the answer, AND the raw value
must never enter the GENERATOR's input context. A RecordingGenerator captures
exactly what context the model saw — so this test FAILS if masking is moved after
generation or skipped (the bite condition).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.connectors.bigquery import FakeBigQueryClient, GuardedBigQuery  # noqa: E402
from rag_engine.generation.openai_compat import FakeSqlGenerator  # noqa: E402
from rag_engine.texttosql.agent import TextToSqlAgent  # noqa: E402

_RAW_EMAIL = "jane.doe@example.com"
_PART = "ss_sold_date_sk"
_CAP = 1_000_000_000


class RecordingGenerator:
    """Answer generator that records EXACTLY the rows it was given as context."""

    def __init__(self) -> None:
        self.last_context = ""

    def answer_rows(self, question, rows):
        self.last_context = str(rows)   # the exact context handed to the "model"
        return f"answered from {len(rows)} rows"


def _agent(answer_generator, rows):
    gen = FakeSqlGenerator({
        "customer contacts": f"SELECT customer_email FROM s WHERE {_PART} >= '2024-01-01'"
    })
    fake_bq = FakeBigQueryClient(dry_run_bytes=10, rows=rows)
    g = GuardedBigQuery(fake_bq, _PART, _CAP)
    return TextToSqlAgent(gen, g, masked_columns=("customer_email",),
                          answer_generator=answer_generator)


def test_masked_column_never_reaches_generator_input():
    rec = RecordingGenerator()
    agent = _agent(rec, rows=[{"customer_email": _RAW_EMAIL}])
    res = agent.answer("customer contacts", mask=True)
    # the raw email NEVER entered the model context...
    assert _RAW_EMAIL not in rec.last_context, "LEAK: raw PII reached the model input"
    # ...and the redaction token DID
    assert "[REDACTED]" in rec.last_context
    # ...and is absent from the answer + the returned rows
    assert _RAW_EMAIL not in res.answer
    assert _RAW_EMAIL not in str(res.rows)
    assert any(r["customer_email"] == "[REDACTED]" for r in res.rows)


def test_cleared_session_gets_raw_via_mask_false():
    # an L4+ cleared session (mask=False) receives the raw column — the agent isn't
    # over-masking; governance (mask flag) decides.
    rec = RecordingGenerator()
    agent = _agent(rec, rows=[{"customer_email": _RAW_EMAIL}])
    res = agent.answer("customer contacts", mask=False)
    assert _RAW_EMAIL in rec.last_context   # cleared -> raw reaches the model
    assert res.rows[0]["customer_email"] == _RAW_EMAIL


def test_agent_cannot_run_unsafe_sql():
    # the agent only emits guarded SQL; an unsafe draft is REFUSED before execute.
    from rag_engine.sql.ast_gate import AstGateError
    gen = FakeSqlGenerator({"evil": "DROP TABLE s"})
    fake_bq = FakeBigQueryClient(dry_run_bytes=1)
    g = GuardedBigQuery(fake_bq, _PART, _CAP)
    agent = TextToSqlAgent(gen, g, masked_columns=())
    with pytest.raises(AstGateError):
        agent.answer("evil")
    assert not fake_bq.executed   # never ran


# ---- CRITICAL-fix E2E: alias/case/expr/* never leak via the full agent path ----


@pytest.mark.parametrize("sql,row", [
    ("SELECT customer_email AS em FROM s WHERE ss_sold_date_sk >= '2024-01-01'",
     {"em": _RAW_EMAIL}),                                                   # alias
    ("SELECT customer_email FROM s WHERE ss_sold_date_sk >= '2024-01-01'",
     {"CUSTOMER_EMAIL": _RAW_EMAIL}),                                       # case
    ("SELECT UPPER(customer_email) AS u FROM s WHERE ss_sold_date_sk >= '2024-01-01'",
     {"u": _RAW_EMAIL}),                                                    # expression
    ("SELECT * FROM s WHERE ss_sold_date_sk >= '2024-01-01'",
     {"customer_email": _RAW_EMAIL, "fare": 1.0}),                          # star
])
def test_pii_bypass_vectors_never_reach_generator(sql, row):
    rec = RecordingGenerator()
    gen = FakeSqlGenerator({"q": sql})
    fake_bq = FakeBigQueryClient(dry_run_bytes=10, rows=[row])
    g = GuardedBigQuery(fake_bq, _PART, _CAP)
    agent = TextToSqlAgent(gen, g, masked_columns=("customer_email",),
                           answer_generator=rec)
    res = agent.answer("q", mask=True)
    # raw PII NEVER in the model input, the answer, or the returned rows
    assert _RAW_EMAIL not in rec.last_context, f"LEAK to model via: {sql}"
    assert _RAW_EMAIL not in res.answer
    assert _RAW_EMAIL not in str(res.rows)
    assert "[REDACTED]" in rec.last_context


@pytest.mark.parametrize("unsafe", [
    "INSERT INTO s (a) VALUES (1)",
    "UPDATE s SET a = 1 WHERE ss_sold_date_sk >= '2024-01-01'",
    "SELECT a FROM s WHERE ss_sold_date_sk >= '2024-01-01'; DROP TABLE s",  # multi-statement
    "SELECT a INTO exfil FROM s WHERE ss_sold_date_sk >= '2024-01-01'",      # CTAS-in-disguise
])
def test_agent_refuses_non_drop_unsafe_sql(unsafe):
    # the agent only emits guarded SQL — INSERT/UPDATE/stacked/INTO are all refused
    # before execute (not just DROP).
    from rag_engine.sql.ast_gate import AstGateError
    gen = FakeSqlGenerator({"q": unsafe})
    fake_bq = FakeBigQueryClient(dry_run_bytes=1)
    g = GuardedBigQuery(fake_bq, _PART, _CAP)
    agent = TextToSqlAgent(gen, g, masked_columns=())
    with pytest.raises(AstGateError):
        agent.answer("q")
    assert not fake_bq.executed   # never ran

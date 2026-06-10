"""TextToSqlAgent — NL question -> guarded read-only SQL -> MASKED rows -> answer.

Flow per question:
  1. draft SQL via the SqlGenerator (Fake for tests; Groq/NVIDIA live),
  2. run it through ``GuardedBigQuery`` (P0.3a: read-only AST gate + cost guard) —
     the agent can ONLY emit guarded SQL; an unsafe draft raises and never runs,
  3. MASK the result rows (🔴 hard gate — BEFORE they become model context),
  4. answer from the MASKED rows (an answer generator that only ever sees masked
     values; raw masked-column values never reach the model).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..catalog.asset import ColumnPolicy
from ..sql.ast_gate import assert_read_only, projection_sources
from .result_masking import mask_rows


class AnswerFromRows(Protocol):
    def answer_rows(self, question: str, rows: list[dict[str, Any]]) -> str:
        ...


class _ExtractiveRowAnswerer:
    """Default answerer: render the (already-masked) rows into a grounded answer."""

    def answer_rows(self, question: str, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ("Access Denied due to security clearances, or no rows matched "
                    "this request.")
        body = "; ".join(", ".join(f"{k}={v}" for k, v in r.items()) for r in rows[:5])
        return f"{body}\n\n(Grounded in {len(rows)} warehouse row(s).)"


@dataclass(slots=True)
class SqlAnswer:
    question: str
    sql: str
    rows: list[dict[str, Any]]      # the MASKED rows handed to the model
    answer: str
    masked: bool
    columns: tuple[ColumnPolicy, ...] = field(default_factory=tuple)


class TextToSqlAgent:
    def __init__(
        self,
        sql_generator,
        guarded_bq,
        masked_columns: tuple[str, ...] = (),
        column_policies: tuple[ColumnPolicy, ...] | None = None,
        answer_generator: AnswerFromRows | None = None,
    ) -> None:
        self.sql_generator = sql_generator
        self.guarded_bq = guarded_bq
        # column policies for masking: either passed explicitly, or synthesized
        # from masked_columns (PII_MASK default).
        if column_policies is not None:
            self.columns = column_policies
        else:
            self.columns = tuple(
                ColumnPolicy(name=c, pii=True, masked=True, mask_reason="PII_MASK")
                for c in masked_columns
            )
        self.answer_generator = answer_generator or _ExtractiveRowAnswerer()

    def answer(self, question: str, mask: bool = True) -> SqlAnswer:
        # 1. draft SQL
        sql = self.sql_generator.draft_sql(question)
        # 2. validate via the AST gate FIRST (raises on unsafe SQL) and extract the
        #    projection->source map — masking is driven by SOURCE columns, not the
        #    LLM-chosen output keys (defeats alias/case/expr/* PII bypasses).
        tree = assert_read_only(sql, dialect=self.guarded_bq.dialect)
        projections = projection_sources(tree)
        # 3. run through the guard (cost guard etc.); the same validated SQL runs
        raw_rows = self.guarded_bq.run(sql)
        raw_rows = [dict(r) for r in raw_rows] if raw_rows else []
        # 4. 🔴 MASK by AST source BEFORE the model sees the rows
        masked = mask_rows(raw_rows, self.columns, mask=mask, projections=projections)
        # 5. answer from the MASKED rows only
        answer = self.answer_generator.answer_rows(question, masked)
        return SqlAnswer(question=question, sql=sql, rows=masked, answer=answer,
                         masked=mask, columns=self.columns)

"""SQL-drafting generators (NL question -> SQL string) for the text-to-SQL agent.

Two implementations behind a common ``SqlGenerator`` shape:
  * ``FakeSqlGenerator`` — deterministic NL->SQL map for tests (NO creds).
  * ``OpenAICompatGenerator`` — Groq / NVIDIA NIM (OpenAI-compatible), live path,
    base_url + model from config; creds-gated.

The drafted SQL is ALWAYS validated by the P0.3a ``GuardedBigQuery`` before it can
run — the LLM cannot emit non-SELECT/unsafe SQL past the gate.
"""

from __future__ import annotations

from typing import Protocol


class SqlGenerator(Protocol):
    def draft_sql(self, question: str) -> str:
        """Draft a (candidate) SQL string for the NL question."""
        ...


class FakeSqlGenerator:
    """Deterministic NL->SQL map for tests. Unknown question -> a benign SELECT 1."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._map = dict(mapping)

    def draft_sql(self, question: str) -> str:
        return self._map.get(question, "SELECT 1")


class OpenAICompatGenerator:
    """Groq / NVIDIA NIM SQL drafter (OpenAI-compatible). Live, creds-gated."""

    def __init__(self, base_url: str, model: str, api_key: str,
                 system_prompt: str | None = None) -> None:
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.system_prompt = system_prompt or (
            "You translate the user's question into a single read-only BigQuery "
            "SELECT. Always filter on the partition column. Never emit DML/DDL."
        )

    def draft_sql(self, question: str) -> str:  # pragma: no cover - live path
        from openai import OpenAI

        client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content.strip()

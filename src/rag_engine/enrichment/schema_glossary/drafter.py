"""Glossary drafters + the build pipeline (P0.4).

The drafter proposes a meaning for a physical column the view-miner couldn't
resolve, using the profiler's hints. ``FakeGlossaryDrafter`` is a deterministic
map for tests (no creds); ``LlmGlossaryDrafter`` calls the Groq/NVIDIA generator
(live, creds-gated). ``build_glossary`` merges view-mined evidence (HIGH
confidence) with LLM drafts (LOW confidence, until human-approved); mined wins.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from .glossary import Glossary, GlossaryEntry
from .profiler import ColumnProfile


class GlossaryDrafter(Protocol):
    def draft(self, table: str, physical: str, profile: ColumnProfile) -> str | None:
        """Propose a meaning for (table, physical), or None if it can't."""
        ...


class FakeGlossaryDrafter:
    """Deterministic (table, physical) -> meaning map for tests."""

    def __init__(self, mapping: Mapping[tuple[str, str], str]) -> None:
        self._map = dict(mapping)

    def draft(self, table: str, physical: str, profile: ColumnProfile) -> str | None:
        return self._map.get((table, physical))


class LlmGlossaryDrafter:  # pragma: no cover - live path
    """Groq/NVIDIA glossary drafter (OpenAI-compatible). Creds-gated."""

    def __init__(self, base_url: str, model: str, api_key: str) -> None:
        self.base_url, self.model, self.api_key = base_url, model, api_key

    def draft(self, table: str, physical: str, profile: ColumnProfile) -> str | None:
        from openai import OpenAI

        client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        prompt = (
            f"Physical column {table}.{physical} has value profile: "
            f"class={profile.regex_class}, distinct_ratio={profile.distinct_ratio}, "
            f"null_rate={profile.null_rate}. Propose a concise semantic name "
            f"(snake_case, e.g. customer_email). Reply with ONLY the name."
        )
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return resp.choices[0].message.content.strip() or None


def build_glossary(
    profiles: Mapping[str, ColumnProfile],
    mined_views: Mapping[tuple[str, str], str],
    drafter: GlossaryDrafter,
) -> Glossary:
    """Merge view-mined (HIGH) + LLM-drafted (LOW) entries into one glossary."""
    g = Glossary()
    # 1. view-mined evidence -> HIGH confidence
    for (table, physical), meaning in mined_views.items():
        g.add(GlossaryEntry(physical=physical, table=table, means=meaning,
                            confidence="high", source="view"))
    # 2. fill gaps with LLM drafts -> LOW confidence (human-approve to raise)
    for physical, prof in profiles.items():
        if g.get(prof.table, physical) is not None:
            continue  # already mined (HIGH) -> mined wins
        meaning = drafter.draft(prof.table, physical, prof)
        if meaning:
            g.add(GlossaryEntry(physical=physical, table=prof.table, means=meaning,
                                confidence="low", source="llm"))
    return g

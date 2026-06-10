"""GlossaryEntry + the in-memory Glossary store (P0.4).

A glossary entry maps a PHYSICAL column (``tbl_44.text_2``) to its MEANING
("full_name") with synonyms/examples + a confidence flag and a provenance source.
Keying is per (table, physical) — the SAME physical name can mean different things
in different tables (``tbl_44.text_2``=full_name vs ``tbl_71.text_2``=order_status),
which is the whole point of the opaque-schema problem.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GlossaryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    physical: str                      # e.g. "text_2"
    table: str                         # e.g. "tbl_44"
    means: str                         # e.g. "full_name"
    synonyms: tuple[str, ...] = Field(default_factory=tuple)
    examples: tuple[str, ...] = Field(default_factory=tuple)
    # "high" (view-mined / human-approved) | "low" (LLM-drafted, until validated)
    confidence: str = "low"
    source: str = ""                   # "view" | "llm" | "profiler" | "human"
    join_paths: tuple[str, ...] = Field(default_factory=tuple)

    @property
    def key(self) -> tuple[str, str]:
        return (self.table, self.physical)


class Glossary:
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], GlossaryEntry] = {}

    def add(self, entry: GlossaryEntry) -> None:
        self._by_key[entry.key] = entry

    def get(self, table: str, physical: str) -> GlossaryEntry | None:
        return self._by_key.get((table, physical))

    def all(self) -> list[GlossaryEntry]:
        return [self._by_key[k] for k in sorted(self._by_key)]

    def by_meaning(self, meaning: str) -> list[GlossaryEntry]:
        m = meaning.strip().casefold()
        out = []
        for e in self.all():
            hay = {e.means.casefold(), *(s.casefold() for s in e.synonyms)}
            if m in hay:
                out.append(e)
        return out

    def __len__(self) -> int:
        return len(self._by_key)

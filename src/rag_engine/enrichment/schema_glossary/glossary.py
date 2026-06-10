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


class SurrealGlossaryStore:
    """Persist/load the glossary in SurrealDB (the governed glossary store, §3.3).

    Entries live in a ``glossary`` table keyed by ``<table>__<physical>``; reload
    reconstructs an in-memory ``Glossary``. RecordID-param bound (no injection).
    """

    def __init__(self, store) -> None:
        self.store = store

    @staticmethod
    def _rid(table: str, physical: str):
        from surrealdb import RecordID

        return RecordID("glossary", f"{table}__{physical}")

    def save(self, glossary: Glossary) -> int:
        n = 0
        for e in glossary.all():
            self.store._db.query(
                "UPSERT $rid CONTENT $data;",
                {"rid": self._rid(e.table, e.physical),
                 "data": {"physical": e.physical, "table": e.table, "means": e.means,
                          "synonyms": list(e.synonyms), "examples": list(e.examples),
                          "confidence": e.confidence, "source": e.source,
                          "join_paths": list(e.join_paths)}},
            )
            n += 1
        return n

    def load(self) -> Glossary:
        rows = self.store._db.query("SELECT * FROM glossary;")
        g = Glossary()
        for row in (rows or []):
            g.add(GlossaryEntry(
                physical=row["physical"], table=row["table"], means=row["means"],
                synonyms=tuple(row.get("synonyms", [])),
                examples=tuple(row.get("examples", [])),
                confidence=row.get("confidence", "low"), source=row.get("source", ""),
                join_paths=tuple(row.get("join_paths", [])),
            ))
        return g

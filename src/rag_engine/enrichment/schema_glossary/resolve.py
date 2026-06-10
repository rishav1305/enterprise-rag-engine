"""Glossary resolver — NL term -> (table, physical) over the opaque schema (P0.4).

This is what lets text-to-SQL retrieve over the GLOSSARY, not the raw schema: a
question about "customer name" resolves to ``(tbl_44, text_2)`` so the agent writes
``SELECT text_2 FROM tbl_44`` correctly. Per-table aware: "order status" resolves to
``(tbl_71, text_2)``, NOT ``tbl_44``.
"""

from __future__ import annotations

from .glossary import Glossary, GlossaryEntry


class GlossaryResolver:
    def __init__(self, glossary: Glossary) -> None:
        self.glossary = glossary

    def resolve(self, nl_term: str, table: str | None = None) -> tuple[str, str] | None:
        """Return (table, physical) for an NL term (meaning or synonym), or None.

        When ``table`` is given, only that table's entries are considered (per-table
        disambiguation). Prefers HIGH-confidence entries over LOW.
        """
        matches = self.glossary.by_meaning(nl_term)
        if table is not None:
            matches = [e for e in matches if e.table == table]
        if not matches:
            return None
        best = sorted(matches, key=lambda e: (e.confidence != "high", e.table, e.physical))[0]
        return (best.table, best.physical)

    def entry(self, nl_term: str, table: str | None = None) -> GlossaryEntry | None:
        key = self.resolve(nl_term, table)
        return self.glossary.get(*key) if key else None

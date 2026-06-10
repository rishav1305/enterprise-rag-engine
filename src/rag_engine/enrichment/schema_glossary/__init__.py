"""Opaque-schema semantic glossary (P0.4) — turn `tbl_44.text_2` into "full_name".

profiler (value stats) + view_miner (sqlglot lineage) + drafter (LLM) build a
governed, per-table glossary (stored in SurrealDB); the resolver lets text-to-SQL
retrieve over the GLOSSARY, not the raw opaque schema. S3 verdict: first-party build.
"""

from .glossary import Glossary, GlossaryEntry
from .profiler import ColumnProfile, profile_column, profile_table
from .view_miner import mine_views

__all__ = [
    "Glossary", "GlossaryEntry", "ColumnProfile",
    "profile_column", "profile_table", "mine_views",
]

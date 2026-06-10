"""SurrealDB schema DDL (3.1.x syntax, verified by spike S2).

All DEFINEs use OVERWRITE so the schema can be re-applied idempotently (the
spike confirmed `DELETE`/re-`DEFINE` on existing objects errors). 3.x specifics:
vector index is HNSW … TYPE F32 (not standalone MTREE … DIST); full-text is
FULLTEXT ANALYZER … BM25 (not SEARCH ANALYZER).

vector_dim defaults to Voyage-3-large's 1024 (matches the TurboVec index); the
vectors-by-id live here while TurboVec serves the ANN (per S2).
"""

from __future__ import annotations

VECTOR_DIM = 1024  # Voyage-3-large


def ddl_statements(vector_dim: int = VECTOR_DIM) -> list[str]:
    return [
        "DEFINE TABLE OVERWRITE asset SCHEMALESS;",
        "DEFINE TABLE OVERWRITE chunk SCHEMALESS;",
        "DEFINE TABLE OVERWRITE supplier SCHEMALESS;",
        "DEFINE TABLE OVERWRITE contract SCHEMALESS;",
        "DEFINE TABLE OVERWRITE component SCHEMALESS;",
        "DEFINE TABLE OVERWRITE ticket SCHEMALESS;",
        # Graph edge between chunks (P0.6 graph mode). A directed `links` edge so
        # traversal (`chunk:a->links->chunk:b`) resolves to chunk ids — the same
        # governance currency the allowlist pre-filter is keyed on.
        "DEFINE TABLE OVERWRITE links SCHEMALESS TYPE RELATION FROM chunk TO chunk;",
        "DEFINE ANALYZER OVERWRITE meridian_text TOKENIZERS blank,class FILTERS lowercase;",
        (
            f"DEFINE INDEX OVERWRITE chunk_vec ON chunk FIELDS vec "
            f"HNSW DIMENSION {vector_dim} DIST COSINE TYPE F32;"
        ),
        (
            "DEFINE INDEX OVERWRITE ticket_ft ON ticket FIELDS summary "
            "FULLTEXT ANALYZER meridian_text BM25;"
        ),
        # Full-text over chunk text (P0.6 lexical mode). Lexical hits resolve to
        # chunk ids so the same allowlist pre-filter applies (drop-before-search).
        (
            "DEFINE INDEX OVERWRITE chunk_ft ON chunk FIELDS text "
            "FULLTEXT ANALYZER meridian_text BM25;"
        ),
    ]

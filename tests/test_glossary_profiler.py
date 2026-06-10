"""P0.4 WORKER-A — profiler value-stat cases over legacy_mart fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from rag_engine.enrichment.schema_glossary.profiler import (  # noqa: E402
    profile_column, profile_table,
)


def test_email_column_classified():
    rows = [{"text_5": f"u{i}@example.com"} for i in range(30)]
    p = profile_column(rows, "tbl_44", "text_5")
    assert p.regex_class == "email"
    assert p.distinct_ratio == 1.0


def test_name_column_classified():
    rows = [{"text_2": n} for n in ["Jane Doe", "John Smith", "Mary Major"] * 5]
    p = profile_column(rows, "tbl_44", "text_2")
    assert p.regex_class == "name"


def test_enum_low_cardinality():
    rows = [{"text_2": s} for s in ["placed", "shipped", "returned"] * 20]
    p = profile_column(rows, "tbl_71", "text_2")
    assert p.regex_class == "enum"
    assert p.distinct_ratio < 0.2


def test_numeric_column():
    rows = [{"num_7": round(i * 1.5, 2)} for i in range(40)]
    p = profile_column(rows, "tbl_71", "num_7")
    assert p.regex_class == "numeric"


def test_null_rate_computed():
    rows = [{"text_5": "x@y.com"}] * 8 + [{"text_5": None}] * 2
    p = profile_column(rows, "tbl_44", "text_5")
    assert abs(p.null_rate - 0.2) < 1e-9


def test_empty_column():
    rows = [{"c": None}, {"c": None}]
    assert profile_column(rows, "t", "c").regex_class == "empty"


def test_profile_table_covers_all_columns():
    rows = [{"text_1": "id-1", "text_2": "Jane Doe", "num_3": 2}]
    profs = profile_table(rows, "tbl_44")
    assert set(profs) == {"text_1", "text_2", "num_3"}
    assert all(p.table == "tbl_44" for p in profs.values())


def test_high_cardinality_id_distinct_ratio_one():
    rows = [{"text_1": f"id-{i}"} for i in range(100)]
    assert profile_column(rows, "tbl_44", "text_1").distinct_ratio == 1.0

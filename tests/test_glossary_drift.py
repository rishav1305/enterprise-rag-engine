"""P0.4 WORKER-C — glossary drift detection cases."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_engine.enrichment.schema_glossary.drift import detect_drift  # noqa: E402
from rag_engine.enrichment.schema_glossary.glossary import Glossary, GlossaryEntry  # noqa: E402


def _glossary(*keys):
    g = Glossary()
    for table, physical, means in keys:
        g.add(GlossaryEntry(physical=physical, table=table, means=means, confidence="high"))
    return g


def test_clean_when_schema_matches():
    g = _glossary(("tbl_44", "text_2", "full_name"))
    d = detect_drift(g, [("tbl_44", "text_2")])
    assert d.is_clean and not d.new_columns and not d.vanished_entries


def test_new_column_flagged():
    g = _glossary(("tbl_44", "text_2", "full_name"))
    d = detect_drift(g, [("tbl_44", "text_2"), ("tbl_44", "text_9")])
    assert ("tbl_44", "text_9") in d.new_columns
    assert not d.is_clean


def test_vanished_column_flagged():
    # a renamed/dropped column -> the glossary entry is now stale
    g = _glossary(("tbl_44", "text_2", "full_name"))
    d = detect_drift(g, [("tbl_44", "renamed_col")])
    assert ("tbl_44", "text_2") in d.vanished_entries
    assert not d.is_clean


def test_per_table_drift_isolated():
    # text_2 in tbl_71 is fine; only tbl_44's missing text_2 is flagged
    g = _glossary(("tbl_44", "text_2", "name"), ("tbl_71", "text_2", "status"))
    d = detect_drift(g, [("tbl_71", "text_2")])
    assert ("tbl_44", "text_2") in d.vanished_entries
    assert ("tbl_71", "text_2") not in d.vanished_entries


def test_drift_both_directions():
    g = _glossary(("tbl_44", "text_2", "name"))
    d = detect_drift(g, [("tbl_44", "text_9")])
    assert ("tbl_44", "text_9") in d.new_columns        # added
    assert ("tbl_44", "text_2") in d.vanished_entries   # gone

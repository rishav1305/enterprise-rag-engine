"""P0.4 Batch-A inline tests (glossary, profiler, miner, drafter). WORKER-A/B/C extend."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def test_glossary_entry_and_store_per_table():
    from rag_engine.enrichment.schema_glossary.glossary import Glossary, GlossaryEntry
    g = Glossary()
    g.add(GlossaryEntry(physical="text_2", table="tbl_44", means="full_name",
                        synonyms=("name", "customer name"), confidence="high",
                        source="view"))
    g.add(GlossaryEntry(physical="text_2", table="tbl_71", means="order_status",
                        confidence="high", source="view"))
    assert g.get("tbl_44", "text_2").means == "full_name"     # PER-TABLE: same name...
    assert g.get("tbl_71", "text_2").means == "order_status"  # ...different meaning
    assert g.get("tbl_44", "nope") is None


def test_profiler_value_stats():
    from rag_engine.enrichment.schema_glossary.profiler import profile_column
    rows = [{"text_5": f"u{i}@example.com"} for i in range(20)]
    rows += [{"text_5": None}]
    p = profile_column(rows, "tbl_44", "text_5")
    assert p.regex_class == "email"          # detected @-pattern
    assert p.null_rate > 0
    # id-like column: high cardinality
    idrows = [{"text_1": f"id-{i}"} for i in range(50)]
    pid = profile_column(idrows, "tbl_44", "text_1")
    assert pid.distinct_ratio == 1.0


def test_view_miner_per_table():
    from rag_engine.enrichment.schema_glossary.view_miner import mine_views
    views = {"v_cust": "SELECT text_2 AS name FROM tbl_44",
             "v_orders": "SELECT text_2 AS status FROM tbl_71"}
    ev = mine_views(views)
    assert ev[("tbl_44", "text_2")] == "name"
    assert ev[("tbl_71", "text_2")] == "status"


def test_build_glossary_merges_mined_and_drafted():
    from rag_engine.enrichment.schema_glossary.drafter import (
        FakeGlossaryDrafter, build_glossary,
    )
    from rag_engine.enrichment.schema_glossary.profiler import profile_table
    rows44 = [{"text_2": "Jane Doe", "text_5": "jane@example.com"} for _ in range(5)]
    profiles = profile_table(rows44, "tbl_44")
    mined = {("tbl_44", "text_2"): "name"}      # view-mined (HIGH)
    drafter = FakeGlossaryDrafter({("tbl_44", "text_5"): "email"})  # LLM-drafted (LOW)
    gl = build_glossary(profiles, mined, drafter)
    assert gl.get("tbl_44", "text_2").confidence == "high"   # mined wins
    assert gl.get("tbl_44", "text_5").means == "email"
    assert gl.get("tbl_44", "text_5").confidence == "low"    # drafted -> low until approved


def test_config_glossary_drafter_backend():
    from rag_engine.config import EngineConfig
    cfg = EngineConfig()
    assert cfg.glossary_drafter in ("fake", "groq", "nvidia")

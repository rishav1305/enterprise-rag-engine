"""P0.4 WORKER-B — view miner (sqlglot lineage) incl. per-table disambiguation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from rag_engine.enrichment.schema_glossary.view_miner import mine_views  # noqa: E402


def test_per_table_same_name_different_meaning():
    ev = mine_views({"v_cust": "SELECT text_2 AS name FROM tbl_44",
                     "v_orders": "SELECT text_2 AS status FROM tbl_71"})
    assert ev[("tbl_44", "text_2")] == "name"
    assert ev[("tbl_71", "text_2")] == "status"


def test_multi_projection_view():
    ev = mine_views({"v": "SELECT text_1 AS customer_id, text_2 AS name, "
                          "text_5 AS email FROM tbl_44"})
    assert ev[("tbl_44", "text_1")] == "customer_id"
    assert ev[("tbl_44", "text_2")] == "name"
    assert ev[("tbl_44", "text_5")] == "email"


def test_real_legacy_views_from_estate():
    # mine the actual LEGACY_VIEWS the estate ships
    sys.path.insert(0, str(ROOT))
    from seeds.synthetic.legacy_mart import LEGACY_VIEWS
    ev = mine_views(LEGACY_VIEWS)
    assert ev[("tbl_44", "text_2")] == "name"
    assert ev[("tbl_44", "text_5")] == "email"
    assert ev[("tbl_71", "text_2")] == "status"
    assert ev[("tbl_71", "num_7")] == "total"


def test_unaliased_columns_yield_no_evidence():
    # a bare `SELECT text_2 FROM tbl_44` (no AS) provides no meaning mapping
    ev = mine_views({"v": "SELECT text_2 FROM tbl_44"})
    assert ("tbl_44", "text_2") not in ev


def test_expression_projection_ignored():
    # an aliased EXPRESSION (not a bare column) is not direct evidence
    ev = mine_views({"v": "SELECT UPPER(text_2) AS shouty FROM tbl_44"})
    assert ("tbl_44", "text_2") not in ev


def test_unparseable_sql_skipped():
    ev = mine_views({"good": "SELECT text_2 AS name FROM tbl_44", "bad": ";;;"})
    assert ev.get(("tbl_44", "text_2")) == "name"   # good one still mined


def test_multi_table_join_view_not_mined():
    # a JOIN view would let us misattribute a column to the wrong table -> REFUSE.
    ev = mine_views({"v": "SELECT t.text_2 AS name, u.text_2 AS status "
                          "FROM tbl_44 t JOIN tbl_71 u ON t.text_1 = u.fk_text_1"})
    assert ev == {}        # multi-table -> nothing mined (no misattribution)


def test_single_table_with_alias_still_mined():
    # a single-table view with a table alias is still safely mined
    ev = mine_views({"v": "SELECT t.text_2 AS name FROM tbl_44 t WHERE t.text_1 > 'x'"})
    assert ev[("tbl_44", "text_2")] == "name"

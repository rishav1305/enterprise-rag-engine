"""P0.4 HEADLINE — text-to-SQL retrieves over the GLOSSARY, not the raw schema.

NL "customer name" -> glossary -> (tbl_44, text_2) -> `SELECT text_2 FROM tbl_44`
(correct over the opaque schema), executed via GuardedBigQuery, with per-table
masking: tbl_44.text_2 (full_name, PII) -> [REDACTED]; tbl_71.text_2 (order_status)
-> NOT masked. Built from the REAL legacy_mart views + the catalog's per-table
ColumnPolicy.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from rag_engine.catalog.connector import SeedConnector  # noqa: E402
from rag_engine.catalog.registry import CatalogRegistry  # noqa: E402
from rag_engine.connectors.bigquery import FakeBigQueryClient, GuardedBigQuery  # noqa: E402
from rag_engine.enrichment.schema_glossary.drafter import FakeGlossaryDrafter, build_glossary  # noqa: E402
from rag_engine.enrichment.schema_glossary.profiler import profile_table  # noqa: E402
from rag_engine.enrichment.schema_glossary.resolve import GlossaryResolver  # noqa: E402
from rag_engine.enrichment.schema_glossary.view_miner import mine_views  # noqa: E402
from rag_engine.generation.openai_compat import FakeSqlGenerator  # noqa: E402
from rag_engine.texttosql.agent import TextToSqlAgent  # noqa: E402
from seeds.synthetic.legacy_mart import LEGACY_VIEWS  # noqa: E402

_VICTIM = "Jane Doe"


def _catalog_columns(asset_id: str):
    """ColumnPolicy tuple for an asset, from the SEEDED catalog (single source of
    truth — so the per-table-masking assertion tracks the estate, not an inline dup)."""
    reg = CatalogRegistry()
    reg.load(SeedConnector(scale=0.01))
    return reg.get(asset_id).columns


def _glossary():
    rows44 = [{"text_1": "id-1", "text_2": "Jane Doe", "text_5": "j@x.com", "num_3": 2}]
    rows71 = [{"text_1": "ord-1", "num_7": 9.99, "text_2": "shipped"}]
    profiles = {**profile_table(rows44, "tbl_44"), **profile_table(rows71, "tbl_71")}
    mined = mine_views(LEGACY_VIEWS)   # text_2->name (tbl_44), text_2->status (tbl_71)
    return build_glossary(profiles, mined, FakeGlossaryDrafter({}))


def test_nl_customer_name_resolves_to_tbl44_text2():
    r = GlossaryResolver(_glossary())
    assert r.resolve("name") == ("tbl_44", "text_2")          # NL meaning -> physical
    assert r.resolve("status") == ("tbl_71", "text_2")        # per-table: orders, not customers


def test_glossary_drives_correct_sql_over_opaque_schema():
    r = GlossaryResolver(_glossary())
    table, physical = r.resolve("name")                       # -> (tbl_44, text_2)
    sql = f"SELECT {physical} FROM {table} WHERE text_1 >= 'id-0'"
    assert sql == "SELECT text_2 FROM tbl_44 WHERE text_1 >= 'id-0'"
    # the agent runs it through the guard and masks the PER-TABLE PII column
    gen = FakeSqlGenerator({"customer names": sql})
    fake_bq = FakeBigQueryClient(dry_run_bytes=10, rows=[{"text_2": _VICTIM}])
    g = GuardedBigQuery(fake_bq, "text_1", 1_000_000_000)
    # tbl_44.text_2 masking comes from the SEEDED catalog per-table policy (single
    # source) — so flipping the seed's masked flag flips this assertion too.
    agent = TextToSqlAgent(gen, g, column_policies=_catalog_columns("legacy_mart_tbl_44"))
    res = agent.answer("customer names", mask=True)
    assert _VICTIM not in res.answer and _VICTIM not in str(res.rows)
    assert res.rows[0]["text_2"] == "[REDACTED]"


def test_per_table_text2_not_masked_for_orders():
    # tbl_71.text_2 (order_status) is NOT PII -> not masked (per-table semantics),
    # sourced from the seeded catalog's tbl_71 ColumnPolicy (text_2 unmasked there).
    gen = FakeSqlGenerator({"order statuses": "SELECT text_2 FROM tbl_71 WHERE text_1 >= 'o0'"})
    fake_bq = FakeBigQueryClient(dry_run_bytes=10, rows=[{"text_2": "shipped"}])
    g = GuardedBigQuery(fake_bq, "text_1", 1_000_000_000)
    agent = TextToSqlAgent(gen, g, column_policies=_catalog_columns("legacy_mart_tbl_71"))
    res = agent.answer("order statuses", mask=True)
    assert res.rows[0]["text_2"] == "shipped"            # raw status, correctly NOT masked


def test_headline_bites_wrong_table_resolution_caught():
    # if the resolver returned the WRONG table for "name", the SQL would be wrong.
    r = GlossaryResolver(_glossary())
    # "name" must NOT resolve to tbl_71 (orders has no name) -> would be a bad query
    assert r.resolve("name", table="tbl_71") is None
    assert r.resolve("name", table="tbl_44") == ("tbl_44", "text_2")

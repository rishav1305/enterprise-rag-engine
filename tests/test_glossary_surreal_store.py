"""P0.4 — SurrealDB glossary persistence + drift CI gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

pytest.importorskip("surrealdb")

from rag_engine.enrichment.schema_glossary.drafter import (  # noqa: E402
    FakeGlossaryDrafter, build_glossary,
)
from rag_engine.enrichment.schema_glossary.drift import detect_drift  # noqa: E402
from rag_engine.enrichment.schema_glossary.glossary import (  # noqa: E402
    Glossary, GlossaryEntry, SurrealGlossaryStore,
)
from rag_engine.enrichment.schema_glossary.profiler import profile_table  # noqa: E402
from rag_engine.enrichment.schema_glossary.view_miner import mine_views  # noqa: E402
from rag_engine.store.surreal import SurrealStore  # noqa: E402
from seeds.synthetic.legacy_mart import GLOSSARY_TRUTH, LEGACY_VIEWS  # noqa: E402


def _store(surreal_local, db):
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db=db,
                      user="root", password="root")
    st.connect()
    st.apply_schema()
    return st


def test_glossary_roundtrips_through_surreal(surreal_local):
    st = _store(surreal_local, "gloss_rt")
    g = Glossary()
    g.add(GlossaryEntry(physical="text_2", table="tbl_44", means="full_name",
                        synonyms=("name",), confidence="high", source="view"))
    g.add(GlossaryEntry(physical="text_2", table="tbl_71", means="order_status",
                        confidence="high", source="view"))
    gs = SurrealGlossaryStore(st)
    assert gs.save(g) == 2
    loaded = gs.load()
    # per-table semantics survive the round-trip
    assert loaded.get("tbl_44", "text_2").means == "full_name"
    assert loaded.get("tbl_71", "text_2").means == "order_status"
    st.close()


def test_built_glossary_persisted_and_drift_clean(surreal_local):
    st = _store(surreal_local, "gloss_build")
    rows44 = [{"text_1": "id-1", "text_2": "Jane Doe", "text_5": "j@x.com", "num_3": 2}]
    rows71 = [{"text_1": "ord-1", "num_7": 9.99, "text_2": "shipped"}]
    profiles = {**profile_table(rows44, "tbl_44"), **profile_table(rows71, "tbl_71")}
    g = build_glossary(profiles, mine_views(LEGACY_VIEWS), FakeGlossaryDrafter({}))
    SurrealGlossaryStore(st).save(g)
    reloaded = SurrealGlossaryStore(st).load()
    # the mined per-table meanings are present
    assert reloaded.get("tbl_44", "text_2").means == "name"
    assert reloaded.get("tbl_71", "text_2").means == "status"
    st.close()


def test_drift_ci_gate_flags_a_renamed_column():
    # drift-CI: a glossary built from the truth vs a schema with a renamed column
    g = Glossary()
    for key, meaning in GLOSSARY_TRUTH.items():
        if "." not in key:
            continue
        table, physical = key.split(".", 1)
        g.add(GlossaryEntry(physical=physical, table=table, means=meaning,
                            confidence="high", source="view"))
    # current schema renames tbl_44.text_2 -> tbl_44.full_name
    current = [(k.split(".")[0], k.split(".")[1]) for k in GLOSSARY_TRUTH if "." in k]
    current = [(t, "full_name" if (t, c) == ("tbl_44", "text_2") else c) for t, c in current]
    drift = detect_drift(g, current)
    assert not drift.is_clean
    assert ("tbl_44", "text_2") in drift.vanished_entries        # stale entry flagged
    assert ("tbl_44", "full_name") in drift.new_columns          # new physical flagged

"""P0.2a — SurrealConnector parity with SeedConnector (same Connector surface)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_surreal_connector_matches_seed_connector(surreal_local):
    from rag_engine.catalog.connector import SeedConnector
    from rag_engine.catalog.registry import CatalogRegistry
    from rag_engine.catalog.surreal_connector import SurrealConnector
    from rag_engine.store.surreal import SurrealStore
    from seeds.targets.surreal_target import load_estate

    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db="conn",
                      user="root", password="root")
    st.connect()
    st.apply_schema()
    load_estate(st, scale=0.01)

    seed_reg = CatalogRegistry()
    seed_reg.load(SeedConnector(scale=0.01))
    surr_reg = CatalogRegistry()
    surr_reg.load(SurrealConnector(st))

    seed_ids = {a.asset_id for a in seed_reg.all()}
    surr_ids = {a.asset_id for a in surr_reg.all()}
    assert seed_ids == surr_ids  # same 25 assets

    # identical governance footprint per asset (the parity that the oracle rests on)
    for aid in seed_ids:
        s, q = seed_reg.get(aid), surr_reg.get(aid)
        assert q.sensitivity_class == s.sensitivity_class, aid
        assert q.security.clearance_level == s.security.clearance_level, aid
        assert set(q.security.need_to_know_roles) == set(s.security.need_to_know_roles), aid
        assert q.masked_columns() == s.masked_columns(), aid
    st.close()

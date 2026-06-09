"""P0.2a — SurrealDB Cloud profile (multi-setup, real but non-gating).

Marked ``cloud`` + creds-gated: runs ONLY when SURREAL_CLOUD_DSN + creds are in
the environment (`pytest -m cloud`). CI runs `-m "not cloud"`, so the hosted path
is real and exercisable on demand without gating CI on a network service.

Proves the SAME SurrealStore + estate loader + SurrealConnector work against
SurrealDB Cloud exactly as against the local self-host instance — only the DSN
and credentials differ (CONFIGURABLE). Creds come from env, never committed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

_CLOUD_DSN = os.getenv("SURREAL_CLOUD_DSN")
_CLOUD_USER = os.getenv("SURREAL_CLOUD_USER")
_CLOUD_PASS = os.getenv("SURREAL_CLOUD_PASS")


@pytest.mark.cloud
@pytest.mark.skipif(
    not (_CLOUD_DSN and _CLOUD_USER and _CLOUD_PASS),
    reason="SurrealDB Cloud creds not in env (set SURREAL_CLOUD_DSN/USER/PASS)",
)
def test_cloud_estate_load_and_connector_parity():
    pytest.importorskip("surrealdb")
    from rag_engine.catalog.registry import CatalogRegistry
    from rag_engine.catalog.surreal_connector import SurrealConnector
    from rag_engine.store.surreal import SurrealStore
    from seeds.targets.surreal_target import load_estate

    st = SurrealStore(dsn=_CLOUD_DSN, ns="meridian", db="ci_cloud",
                      user=_CLOUD_USER, password=_CLOUD_PASS)
    st.connect()
    st.apply_schema()
    n = load_estate(st, scale=0.005)
    assert n == 26
    assert st.get_asset("hr_records")["cls"] == "F"

    reg = CatalogRegistry()
    reg.load(SurrealConnector(st))
    assert reg.get("hr_records").sensitivity_class == "F"
    assert reg.get("prerelease_financials").security.clearance_level == 4
    st.close()

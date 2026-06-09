"""P0.2a HEADLINE GATE — 210-cell oracle parity across catalog backends.

The leak-audit oracle (15 personas × 14 classes = 210 cells) must yield IDENTICAL
decisions whether the catalog is sourced from the in-process SeedConnector or the
SurrealDB-backed SurrealConnector. This is the regression-parity proof for the
store swap: governance behaviour is independent of where the catalog lives.

We drive the engine's evaluate() using the asset SecurityContext as each backend
produces it, and compare to seeds.emit.build_oracle() ground truth — for BOTH
backends, 0 mismatches.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from rag_engine.governance.access import evaluate  # noqa: E402
from rag_engine.schemas import EnrichedChunk, Session  # noqa: E402
from seeds.emit import build_oracle  # noqa: E402
from seeds.personas import PERSONAS_BY_KEY  # noqa: E402

_SCALE = 0.01


def _registry_seed():
    from rag_engine.catalog.connector import SeedConnector
    from rag_engine.catalog.registry import CatalogRegistry
    reg = CatalogRegistry()
    reg.load(SeedConnector(scale=_SCALE))
    return reg


def _registry_surreal(surreal_local):
    from rag_engine.catalog.registry import CatalogRegistry
    from rag_engine.catalog.surreal_connector import SurrealConnector
    from rag_engine.store.surreal import SurrealStore
    from seeds.targets.surreal_target import load_estate
    st = SurrealStore(dsn=surreal_local["dsn"], ns="meridian", db="parity",
                      user="root", password="root")
    st.connect()
    st.apply_schema()
    load_estate(st, scale=_SCALE)
    reg = CatalogRegistry()
    reg.load(SurrealConnector(st))
    return reg, st


def _one_asset_per_class(registry):
    """Pick one CatalogAsset per sensitivity class from the registry (the asset's
    SecurityContext is what governance sees for that class)."""
    by_class: dict[str, object] = {}
    for a in registry.all():
        by_class.setdefault(a.sensitivity_class, a)
    return by_class


def _run_oracle(registry) -> int:
    """Return (mismatches, cells_covered) vs the oracle ground truth.

    With class H now seeded (P0.2b T-H), every one of the 14 classes has an estate
    asset, so cells_covered must be 14*15 = 210 (no skips) — the full round-trip.
    """
    oracle = build_oracle()["expectations"]
    by_class = _one_asset_per_class(registry)
    mismatches = 0
    cells = 0
    for pkey, persona in PERSONAS_BY_KEY.items():
        sess = Session(user_id=pkey, roles=list(persona.roles),
                       clearance_level=persona.clearance_level)
        for cls, expected in oracle[pkey].items():
            asset = by_class.get(cls)
            if asset is None:
                continue  # should not happen now H is seeded — asserted below
            cells += 1
            chunk = EnrichedChunk(
                chunk_id=f"c-{cls}", parent_doc_id=asset.asset_id,
                parent_title="t", content="x", security=asset.security,
            )
            if evaluate(chunk, sess).decision != expected:
                mismatches += 1
    return mismatches, cells


def test_seed_backend_zero_leaks():
    mismatches, cells = _run_oracle(_registry_seed())
    assert mismatches == 0
    assert cells == 210  # 15 personas x 14 classes, all classes have an asset


def test_surreal_backend_zero_leaks(surreal_local):
    reg, st = _registry_surreal(surreal_local)
    try:
        mismatches, cells = _run_oracle(reg)
        assert mismatches == 0
        assert cells == 210  # full 14-class round-trip through SurrealDB (H seeded)
    finally:
        st.close()


def test_backends_identical_decisions(surreal_local):
    """The strict parity proof: every (persona, class) decision is identical
    whether sourced from SeedConnector or SurrealConnector."""
    oracle = build_oracle()["expectations"]
    seed_by_class = _one_asset_per_class(_registry_seed())
    reg_s, st = _registry_surreal(surreal_local)
    try:
        surr_by_class = _one_asset_per_class(reg_s)
        # both backends must cover the same classes
        assert set(seed_by_class) == set(surr_by_class)
        diffs = []
        for pkey, persona in PERSONAS_BY_KEY.items():
            sess = Session(user_id=pkey, roles=list(persona.roles),
                           clearance_level=persona.clearance_level)
            for cls in oracle[pkey]:
                if cls not in seed_by_class:
                    continue
                sd = evaluate(EnrichedChunk(
                    chunk_id="c", parent_doc_id="d", parent_title="t", content="x",
                    security=seed_by_class[cls].security), sess).decision
                qd = evaluate(EnrichedChunk(
                    chunk_id="c", parent_doc_id="d", parent_title="t", content="x",
                    security=surr_by_class[cls].security), sess).decision
                if sd != qd:
                    diffs.append((pkey, cls, sd, qd))
        assert not diffs, f"backend decision drift: {diffs}"
    finally:
        st.close()

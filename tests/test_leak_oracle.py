"""The leak-audit oracle bound to oracle.json — the regression net.

Drives the engine's governance decision for every (persona × sensitivity class)
and asserts it matches the P0.1a oracle ground truth (seeds.emit.build_oracle).
0 leaks required. This is the net that auto-catches C1/C2-class governance bugs:
if the engine and the oracle ever disagree, a cell fails here.

DRY: the class -> roles/level mapping is imported from the connector
(rag_engine.catalog.connector._CLASS_ROLES), the single source used to build the
asset-level SecurityContexts — never redefined here.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

from seeds.access_matrix import CLASSES  # noqa: E402
from seeds.emit import build_oracle  # noqa: E402
from seeds.personas import PERSONAS_BY_KEY  # noqa: E402
from rag_engine.catalog.connector import _CLASS_ROLES  # noqa: E402  (DRY: single source)
from rag_engine.governance.access import evaluate  # noqa: E402
from rag_engine.schemas import EnrichedChunk, SecurityContext, Session  # noqa: E402

# per-class min clearance level mirrors seeds.access_matrix.CLASSES.min_level
_CLASS_LEVEL = {code: sc.min_level for code, sc in CLASSES.items()}


def _chunk_for(cls: str) -> EnrichedChunk:
    """An asset-level chunk for sensitivity class ``cls`` — same SecurityContext
    the SeedConnector builds, so the engine sees exactly what the catalog holds."""
    roles = _CLASS_ROLES[cls]
    return EnrichedChunk(
        chunk_id=f"c-{cls}", parent_doc_id=f"asset-{cls}", parent_title="t", content="x",
        security=SecurityContext(
            allowed_roles=roles, clearance_level=_CLASS_LEVEL[cls],
            sensitivity_class=cls, need_to_know_roles=roles,
        ),
    )


@pytest.mark.parametrize("persona_key", list(PERSONAS_BY_KEY))
def test_engine_matches_oracle_for_every_class(persona_key):
    oracle = build_oracle()["expectations"][persona_key]
    p = PERSONAS_BY_KEY[persona_key]
    sess = Session(user_id=persona_key, roles=list(p.roles), clearance_level=p.clearance_level)
    for cls, expected in oracle.items():
        got = evaluate(_chunk_for(cls), sess).decision
        assert got == expected, (
            f"LEAK/MISMATCH {persona_key}/{cls}: engine={got!r} oracle={expected!r}"
        )


def test_oracle_covers_full_matrix():
    oracle = build_oracle()["expectations"]
    assert set(oracle) == set(PERSONAS_BY_KEY)  # 14 personas
    for grid in oracle.values():
        assert set(grid) == set(CLASSES)         # 14 classes


def test_sales_manager_customer_pii_is_masked_not_raw():
    # CEO-confirmed (Task 10): Sales Manager sees customer PII MASKED, not raw —
    # least-privilege. World-bible §5 doc aligned to this impl. Pins against drift.
    p = PERSONAS_BY_KEY["sales_manager"]
    sess = Session(user_id="sm", roles=list(p.roles), clearance_level=p.clearance_level)
    assert evaluate(_chunk_for("D"), sess).decision == "mask"
    # raw only at L4+ (e.g. CFO)
    cfo = PERSONAS_BY_KEY["cfo"]
    cfo_sess = Session(user_id="cfo", roles=list(cfo.roles), clearance_level=cfo.clearance_level)
    assert evaluate(_chunk_for("D"), cfo_sess).decision == "allow"


def _decision(persona_key, cls):
    p = PERSONAS_BY_KEY[persona_key]
    sess = Session(user_id=persona_key, roles=list(p.roles), clearance_level=p.clearance_level)
    return evaluate(_chunk_for(cls), sess).decision


def test_i2_support_agent_own_queue_and_masked_pii():
    # I2: §4 intent — customer-facing, sees masked PII. L2 grants C (own queue)
    # + D masked. Doc (§4 L2, §5 C=✓/D=masked) aligned to this.
    assert _decision("support_agent", "C") == "allow"
    assert _decision("support_agent", "D") == "mask"


def test_i2_engineer_customer_pii_masked():
    # I2: Engineer/D = mask (code right; world-bible §5 aligned from ✗ to masked).
    assert _decision("engineer", "D") == "mask"


def test_i2_intern_protagonist_unaffected():
    # the adversarial-leak protagonist stays L1 -> denied C and D.
    assert _decision("intern", "C") == "deny"
    assert _decision("intern", "D") == "deny"

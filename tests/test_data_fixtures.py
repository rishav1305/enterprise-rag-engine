"""P0.1a exit gate — the Meridian Data Foundation reproducibility + coherence
+ masking-policy test surface.

Wave 1 (substrate) assertions pass now. Source-level assertions (volumes,
fields, masking, determinism per source) are added as Wave 2 generators land,
and the full-estate reproducibility + emit assertions as Wave 3 lands.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # so `seeds` imports without install

from seeds import SEED  # noqa: E402
from seeds._coherence import anchors  # noqa: E402
from seeds._rng import derive_rng  # noqa: E402
from seeds.access_matrix import CLASSES, Decision, evaluate_class  # noqa: E402
from seeds.personas import PERSONAS, PERSONAS_BY_KEY  # noqa: E402


# ---- determinism / RNG -------------------------------------------------
def test_derive_rng_is_deterministic():
    a = derive_rng("hr").np.integers(0, 1_000_000, size=50)
    b = derive_rng("hr").np.integers(0, 1_000_000, size=50)
    assert (a == b).all()


def test_sources_are_independent():
    # different source names => different streams (no order coupling)
    a = derive_rng("hr").np.integers(0, 1_000_000, size=20)
    b = derive_rng("crm").np.integers(0, 1_000_000, size=20)
    assert not (a == b).all()


def test_seed_is_fixed():
    assert SEED == 1337


# ---- coherence ---------------------------------------------------------
def test_org_chart_managers_resolve():
    org = anchors().org_chart
    for node in org.values():
        if node.manager_id is not None:
            assert node.manager_id in org, f"dangling manager {node.manager_id}"


def test_org_chart_has_single_root():
    org = anchors().org_chart
    roots = [n for n in org.values() if n.manager_id is None]
    assert len(roots) == 1  # the CEO


def test_segment_revenue_grows_monotonic():
    rev = anchors().segment_revenue
    quarters = list(rev.keys())
    for seg in ("mobility", "marketplace", "pay", "ads"):
        series = [rev[q][seg] for q in quarters]
        assert all(b >= a for a, b in zip(series, series[1:])), f"{seg} not monotonic"


def test_anchors_memoized_stable():
    assert anchors() is anchors()


# ---- personas + access matrix ------------------------------------------
def test_persona_roster_count():
    assert len(PERSONAS) == 13  # world bible §4


def test_non_monotonic_finance_manager_denied_comp():
    # golden scenario #4: high clearance, wrong need-to-know
    fm = PERSONAS_BY_KEY["finance_manager"]
    assert evaluate_class("F", fm.clearance_level, fm.roles) is Decision.DENY


def test_non_monotonic_legal_denied_financials():
    legal = PERSONAS_BY_KEY["legal_counsel"]
    assert evaluate_class("E", legal.clearance_level, legal.roles) is Decision.DENY
    # but legal CAN see legal/M&A (G)
    assert evaluate_class("G", legal.clearance_level, legal.roles) is Decision.ALLOW


def test_cfo_sees_financials_and_comp():
    cfo = PERSONAS_BY_KEY["cfo"]
    assert evaluate_class("E", cfo.clearance_level, cfo.roles) is Decision.ALLOW
    assert evaluate_class("F", cfo.clearance_level, cfo.roles) is Decision.ALLOW


def test_customer_pii_masking_leg():
    # golden scenario #5: analysts get masked, not blocked
    ma = PERSONAS_BY_KEY["marketing_analyst"]
    assert evaluate_class("D", ma.clearance_level, ma.roles) is Decision.MASK
    intern = PERSONAS_BY_KEY["intern"]
    assert evaluate_class("D", intern.clearance_level, intern.roles) is Decision.DENY


def test_intern_denied_sensitive():
    intern = PERSONAS_BY_KEY["intern"]
    for cls in ("E", "F", "G", "H", "I", "M", "N"):
        assert evaluate_class(cls, intern.clearance_level, intern.roles) is Decision.DENY


def test_all_classes_present():
    # A..H + re-included I..N
    assert set(CLASSES) == set("ABCDEFGHIJKLMN")

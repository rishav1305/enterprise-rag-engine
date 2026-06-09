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
from seeds.emit import build_estate, build_oracle, emit  # noqa: E402
from seeds.personas import PERSONAS, PERSONAS_BY_KEY  # noqa: E402
from seeds.synthetic import legacy_mart  # noqa: E402

# small representative scale keeps the gate fast + deterministic
_SCALE = 0.01


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
    assert len(PERSONAS) == 15  # world bible §4 (incl. Strategist + HR Analyst)


def test_scenario_6_strategist_vs_sales_manager_on_mna():
    # golden scenario #6: Strategist ALLOWED M&A (G); Sales Manager DENIED
    strat = PERSONAS_BY_KEY["strategist"]
    sales = PERSONAS_BY_KEY["sales_manager"]
    assert evaluate_class("G", strat.clearance_level, strat.roles) is Decision.ALLOW
    assert evaluate_class("G", sales.clearance_level, sales.roles) is Decision.DENY
    # Strategist must NOT see financials (E) or comp (F)
    assert evaluate_class("E", strat.clearance_level, strat.roles) is Decision.DENY
    assert evaluate_class("F", strat.clearance_level, strat.roles) is Decision.DENY


def test_finance_manager_sees_financials_denied_comp():
    # C2: FM (L4, FINANCE) ✓ E (pre-release financials) but ✗ F (exec comp).
    # This is the non-monotonic teaching point — class E is L4+, not L5.
    fm = PERSONAS_BY_KEY["finance_manager"]
    assert evaluate_class("E", fm.clearance_level, fm.roles) is Decision.ALLOW
    assert evaluate_class("F", fm.clearance_level, fm.roles) is Decision.DENY  # scenario #4


def test_non_monotonic_legal_denied_financials():
    legal = PERSONAS_BY_KEY["legal_counsel"]
    # C2: Legal is L4 but lacks FINANCE need-to-know -> ✗ E
    assert evaluate_class("E", legal.clearance_level, legal.roles) is Decision.DENY
    # but legal CAN see legal/M&A (G)
    assert evaluate_class("G", legal.clearance_level, legal.roles) is Decision.ALLOW


def test_analysts_denied_financials():
    # C2 regression: low-level analysts never see E regardless
    for key in ("data_analyst", "marketing_analyst", "commerce_analyst"):
        p = PERSONAS_BY_KEY[key]
        assert evaluate_class("E", p.clearance_level, p.roles) is Decision.DENY


def test_cfo_sees_financials_and_comp():
    cfo = PERSONAS_BY_KEY["cfo"]
    assert evaluate_class("E", cfo.clearance_level, cfo.roles) is Decision.ALLOW
    assert evaluate_class("F", cfo.clearance_level, cfo.roles) is Decision.ALLOW


def test_ceo_sees_everything():
    # C1: "CEO sees everything" — ALLOW across A..H (incl. security incidents H)
    ceo = PERSONAS_BY_KEY["ceo"]
    for cls in "ABCDEFGH":
        assert evaluate_class(cls, ceo.clearance_level, ceo.roles) is Decision.ALLOW, cls


def test_cfo_denied_security_incidents():
    # C1: CFO is L5 but lacks CISO/SECURITY/BOARD need-to-know -> ✗ H
    cfo = PERSONAS_BY_KEY["cfo"]
    assert evaluate_class("H", cfo.clearance_level, cfo.roles) is Decision.DENY


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


# ---- Wave 3: full-estate reproducibility + coherence + masking ---------
def test_estate_has_all_sources():
    manifest, outputs = build_estate(scale=_SCALE)
    # 19 synthetic (17 sources; legacy_mart splits into tbl_44+tbl_71) + 7 real = 26.
    # (+security_incidents class-H asset added in P0.2b T-H.)
    assert len(manifest.assets) == 26
    assert sum(1 for a in manifest.assets if a.synthetic) == 19
    assert sum(1 for a in manifest.assets if not a.synthetic) == 7


def test_security_incidents_class_H_asset_present():
    manifest, _ = build_estate(scale=_SCALE)
    h = [a for a in manifest.assets if a.sensitivity_class == "H"]
    assert len(h) == 1 and h[0].asset_id == "security_incidents"
    assert h[0].clearance_level == 4  # class H min_level
    assert h[0].vertical == "RISK_SECURITY"


def test_asset_clearance_matches_its_class_min_level():
    # An asset's declared clearance_level must equal its sensitivity class's
    # min_level — otherwise the asset-level gate diverges from the oracle (this
    # caught prerelease_financials declaring L5 while class E is L4). The catalog
    # SecurityContext inherits the asset level, so they must agree.
    #
    # Class D (customer-PII) is EXEMPT: its governance is the masking leg, which
    # keys off the *session* level (mask L2-3, raw L4+), independent of the
    # asset's declared level — so a D asset may declare its raw-access level (e.g.
    # payments KYC raw at L4) without affecting the oracle.
    from seeds.access_matrix import CLASSES
    manifest, _ = build_estate(scale=_SCALE)
    for a in manifest.assets:
        if a.sensitivity_class == "D":
            continue
        expected = CLASSES[a.sensitivity_class].min_level
        assert a.clearance_level == expected, (
            f"{a.asset_id}: declared L{a.clearance_level} != class "
            f"{a.sensitivity_class} min_level L{expected}"
        )


def test_estate_reproducible_byte_identical(tmp_path):
    # THE HARD GATE: emit twice -> byte-identical manifest + rows + oracle
    s1 = emit(tmp_path / "run1", scale=_SCALE)
    s2 = emit(tmp_path / "run2", scale=_SCALE)
    assert s1["total_rows"] == s2["total_rows"]
    for name in ("manifest.json", "oracle.json", "glossary_truth.json"):
        a = (tmp_path / "run1" / name).read_bytes()
        b = (tmp_path / "run2" / name).read_bytes()
        assert a == b, f"{name} not byte-identical across runs"
    # every row file identical too
    r1 = sorted((tmp_path / "run1" / "rows").glob("*.jsonl"))
    r2 = sorted((tmp_path / "run2" / "rows").glob("*.jsonl"))
    assert [p.name for p in r1] == [p.name for p in r2]
    for p1, p2 in zip(r1, r2):
        assert p1.read_bytes() == p2.read_bytes(), f"{p1.name} not reproducible"


def test_masking_policy_schema_complete():
    # SCHEMA-level only: every asset with PII fields declares >=1 maskable field.
    # Runtime masking ENFORCEMENT (redaction at retrieval) is P0.1b's column-masking.
    manifest, _ = build_estate(scale=_SCALE)
    assert manifest.validate_masking() == []  # zero violations


def test_coherence_org_chart_referential_integrity():
    _, outputs = build_estate(scale=1.0)  # full org for integrity check
    hr_rows = outputs["hr_records"].rows
    for r in hr_rows:
        if r["manager_id"]:
            assert r["manager_id"] in anchors().org_chart


def test_coherence_financials_roll_up_from_revenue():
    _, outputs = build_estate(scale=_SCALE)
    fin = outputs["prerelease_financials"].rows
    rev = anchors().segment_revenue
    for row in fin:
        # projection must be >= actual (deterministic optimism factor) and actual
        # must equal the coherence anchor revenue for that quarter+segment
        assert row["actual_revenue"] == rev[row["quarter"]][row["segment"]]
        assert row["projection"] >= row["actual_revenue"]


def test_real_fixtures_contract():
    manifest, outputs = build_estate(scale=_SCALE)
    real = [a for a in manifest.assets if not a.synthetic]
    for a in real:
        assert a.provenance_url, f"{a.asset_id} missing provenance link"
        assert a.scale_badge, f"{a.asset_id} missing scale badge"
        assert outputs[a.asset_id].rows == []  # queried in place, never materialized
    # Common Crawl is catalog-only (no sample pull)
    assert outputs["common_crawl"].connection["catalog_only"] is True


def test_opaque_schema_seed_present():
    from seeds.manifest import Manifest
    out = legacy_mart.generate(Manifest())
    truth = out.connection["glossary_truth"]
    assert truth["tbl_44.text_2"] == "full_name"
    assert truth["tbl_44.text_5"] == "email"
    assert "v_cust" in out.connection["legacy_views"]


def test_oracle_grid_covers_all_personas_and_classes():
    oracle = build_oracle()
    assert set(oracle["expectations"]) == {p.key for p in PERSONAS}
    for grid in oracle["expectations"].values():
        assert set(grid) == set(CLASSES)


# ---- I1: legacy_mart per-table masking ---------------------------------
def test_legacy_mart_per_table_masking():
    manifest, outputs = build_estate(scale=_SCALE)
    by_id = {a.asset_id: a for a in manifest.assets}
    # tbl_44.text_2 (full_name) IS masked PII
    t44 = {f.name: f for f in by_id["legacy_mart_tbl_44"].fields}
    assert t44["text_2"].pii and t44["text_2"].masked
    assert t44["text_5"].pii and t44["text_5"].masked  # email
    # tbl_71.text_2 (order_status) is NOT PII, NOT masked — the I1 bug fix
    t71 = {f.name: f for f in by_id["legacy_mart_tbl_71"].fields}
    assert not t71["text_2"].pii
    assert not t71["text_2"].masked
    # tbl_71 rows actually carry status values, not names
    sec = outputs["legacy_mart_tbl_44"].connection["secondary_rows"]
    assert all(r["text_2"] in {"placed", "shipped", "returned"} for r in sec)


# ---- I2: field contract — each source covers its §7 key fields ----------
# Minimal key-field sets the world bible §7 requires present (and PII present-but-
# masked, never absent). Extend as sources evolve.
_REQUIRED_FIELDS = {
    "hr_records": {"employee_id", "salary", "manager_id"},
    "payroll_runs": {"employee_id", "gross", "net_pay", "bank_acct"},  # I2: bank_acct
    "crm_pipeline": {"account", "stage", "deal_value", "owner"},
    "payments_ledger": {"txn_id", "amount", "merchant", "kyc_id", "name", "dob", "gov_id"},
    "procurement_graph": {"id", "kind"},
    "prerelease_financials": {"segment", "quarter", "projection", "status"},
    "legal_memos": {"doc_id", "kind", "target", "status"},
}


def test_source_field_contracts():
    manifest, _ = build_estate(scale=_SCALE)
    by_id = {a.asset_id: a for a in manifest.assets}
    for asset_id, required in _REQUIRED_FIELDS.items():
        declared = {f.name for f in by_id[asset_id].fields}
        missing = required - declared
        assert not missing, f"{asset_id} missing required fields: {missing}"


def test_payroll_bank_acct_present_and_masked():
    # I2: §7 requires bank_acct present-and-masked; §10 says PII never just absent.
    manifest, outputs = build_estate(scale=_SCALE)
    by_id = {a.asset_id: a for a in manifest.assets}
    bank = next(f for f in by_id["payroll_runs"].fields if f.name == "bank_acct")
    assert bank.pii and bank.masked
    assert all("bank_acct" in r for r in outputs["payroll_runs"].rows)

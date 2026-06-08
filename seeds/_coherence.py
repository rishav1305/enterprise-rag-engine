"""Shared coherence anchors — computed once, consumed by multiple sources.

This is the *only* intra-phase serial dependency in P0.1a. The Finance cluster
(financials, payments, expenses, tax, treasury) and HR read these anchors so
the numbers cohere across sources:

  * org chart (manager_id tree) is internally consistent  -> HR + graph scenarios
  * segment revenue totals derive from TPC-DS-shaped sales -> financials roll up
  * a fixed date epoch + fiscal calendar                   -> all timestamps align
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ._rng import derive_rng

# Fixed epoch — no wall-clock anywhere in the estate.
EPOCH = date(2024, 1, 1)
FISCAL_QUARTERS = ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4",
                   "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]

# Meridian business segments (world bible §1 business lines).
SEGMENTS = ["mobility", "marketplace", "pay", "ads", "corporate"]


@dataclass(frozen=True, slots=True)
class OrgNode:
    employee_id: str
    dept: str
    manager_id: str | None
    level: int  # clearance contribution / seniority


@dataclass(slots=True)
class CoherenceAnchors:
    org_chart: dict[str, OrgNode]
    segment_revenue: dict[str, dict[str, float]]  # quarter -> segment -> revenue
    exec_ids: list[str] = field(default_factory=list)


def _build_org_chart(n_employees: int = 12000, n_execs: int = 120) -> tuple[dict[str, OrgNode], list[str]]:
    """Deterministic manager tree: execs at the top, employees hang beneath."""
    rng = derive_rng("coherence.org").np
    depts = [
        "FINANCE", "PEOPLE", "SALES", "LEGAL", "ENGINEERING", "MOBILITY_OPS",
        "COMMERCE", "MARKETING", "RISK_SECURITY", "STRATEGY", "KNOWLEDGE_SUPPORT",
    ]
    org: dict[str, OrgNode] = {}
    exec_ids: list[str] = []
    # execs (no manager / report to CEO)
    ceo_id = "EMP-000000"
    org[ceo_id] = OrgNode(ceo_id, "CORPORATE", None, level=5)
    exec_ids.append(ceo_id)
    for i in range(1, n_execs):
        eid = f"EMP-{i:06d}"
        dept = depts[i % len(depts)]
        org[eid] = OrgNode(eid, dept, ceo_id, level=4)
        exec_ids.append(eid)
    # rank-and-file report to a random exec (deterministic)
    for i in range(n_execs, n_employees):
        eid = f"EMP-{i:06d}"
        dept = depts[i % len(depts)]
        mgr = exec_ids[int(rng.integers(0, len(exec_ids)))]
        org[eid] = OrgNode(eid, dept, mgr, level=int(rng.integers(1, 3)))
    return org, exec_ids


def _build_segment_revenue() -> dict[str, dict[str, float]]:
    """Segment revenue per quarter — financials.py rolls these up; payments tie in."""
    rng = derive_rng("coherence.revenue").np
    base = {"mobility": 4.2e8, "marketplace": 6.1e8, "pay": 1.8e8, "ads": 9.0e7, "corporate": 0.0}
    out: dict[str, dict[str, float]] = {}
    growth = 1.0
    for q in FISCAL_QUARTERS:
        growth *= 1.0 + float(rng.uniform(0.02, 0.06))  # deterministic QoQ growth
        out[q] = {seg: round(v * growth, 2) for seg, v in base.items()}
    return out


_ANCHORS: CoherenceAnchors | None = None


def anchors() -> CoherenceAnchors:
    """Memoized singleton — computed once per process, deterministic."""
    global _ANCHORS
    if _ANCHORS is None:
        org, exec_ids = _build_org_chart()
        _ANCHORS = CoherenceAnchors(
            org_chart=org,
            segment_revenue=_build_segment_revenue(),
            exec_ids=exec_ids,
        )
    return _ANCHORS

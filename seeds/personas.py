"""The Meridian demo persona roster (world bible §4).

Each persona carries roles + a clearance level. The leak-audit oracle (bound in
P0.1b) drives every persona against every golden query. Access requires BOTH
sufficient level AND role/need-to-know (see ``access_matrix``) — high level
alone never grants access.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Persona:
    key: str
    title: str
    vertical: str
    clearance_level: int
    roles: tuple[str, ...]


# world bible §4 — 14 personas (incl. Strategist, fixes golden scenario #6)
PERSONAS: tuple[Persona, ...] = (
    Persona("intern", "Intern", "KNOWLEDGE_SUPPORT", 1, ("INTERN", "EMPLOYEE")),
    Persona("support_agent", "Support Agent", "KNOWLEDGE_SUPPORT", 1, ("CUSTOMER_SUPPORT", "EMPLOYEE")),
    Persona("data_analyst", "Data Analyst", "ENGINEERING", 2, ("DATA_ANALYST", "EMPLOYEE")),
    Persona("ops_analyst", "Ops Analyst", "MOBILITY_OPS", 2, ("OPS_ANALYST", "EMPLOYEE")),
    Persona("commerce_analyst", "Commerce Analyst", "COMMERCE", 2, ("COMMERCE_ANALYST", "EMPLOYEE")),
    Persona("marketing_analyst", "Marketing Analyst", "MARKETING", 2, ("MARKETING_ANALYST", "EMPLOYEE")),
    Persona("engineer", "Engineer", "ENGINEERING", 2, ("ENGINEER", "EMPLOYEE")),
    Persona("sales_manager", "Sales Manager", "SALES", 3, ("SALES_MANAGER", "EMPLOYEE")),
    Persona("finance_manager", "Finance Manager", "FINANCE", 4, ("FINANCE", "FINANCE_MANAGER", "EMPLOYEE")),
    Persona("legal_counsel", "Legal Counsel", "LEGAL", 4, ("LEGAL", "EMPLOYEE")),
    Persona("ciso", "CISO", "RISK_SECURITY", 4, ("CISO", "SECURITY", "EMPLOYEE")),
    Persona("strategist", "Strategist", "STRATEGY", 4, ("STRATEGY", "EMPLOYEE")),
    Persona("cfo", "CFO", "FINANCE", 5, ("C_SUITE", "FINANCE", "EMPLOYEE")),
    Persona("ceo", "CEO", "CORPORATE", 5, ("C_SUITE", "EMPLOYEE")),
)

PERSONAS_BY_KEY: dict[str, Persona] = {p.key: p for p in PERSONAS}

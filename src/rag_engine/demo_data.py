"""Runtime-safe demo metadata (P0.11c).

The demo's read-only metadata endpoints (/personas, /glossary) must work in the LEAN
production container (requirements.txt only) — which does NOT install the seed-generation
deps (`faker` etc., pulled transitively by `seeds.synthetic`). So the canonical demo
metadata is duplicated here as plain data, with no heavy imports. It mirrors
`seeds/emit.build_oracle()["personas"]` and `seeds/synthetic/legacy_mart.LEGACY_VIEWS`
(kept in sync; the seed packages remain the source of truth for the leak oracle/tests).
"""

from __future__ import annotations

# 15 personas — title / roles / clearance (matches build_oracle()["personas"]).
DEMO_PERSONAS: list[dict] = [
    {"key": "intern", "title": "Intern", "roles": ["INTERN", "EMPLOYEE"], "clearance": 1},
    {"key": "support_agent", "title": "Support Agent", "roles": ["CUSTOMER_SUPPORT", "EMPLOYEE"], "clearance": 2},
    {"key": "data_analyst", "title": "Data Analyst", "roles": ["DATA_ANALYST", "EMPLOYEE"], "clearance": 2},
    {"key": "ops_analyst", "title": "Ops Analyst", "roles": ["OPS_ANALYST", "EMPLOYEE"], "clearance": 2},
    {"key": "commerce_analyst", "title": "Commerce Analyst", "roles": ["COMMERCE_ANALYST", "EMPLOYEE"], "clearance": 2},
    {"key": "marketing_analyst", "title": "Marketing Analyst", "roles": ["MARKETING_ANALYST", "EMPLOYEE"], "clearance": 2},
    {"key": "engineer", "title": "Engineer", "roles": ["ENGINEERING", "EMPLOYEE"], "clearance": 2},
    {"key": "sales_manager", "title": "Sales Manager", "roles": ["SALES_MANAGER", "EMPLOYEE"], "clearance": 3},
    {"key": "hr_analyst", "title": "HR Analyst", "roles": ["HR", "EMPLOYEE"], "clearance": 4},
    {"key": "finance_manager", "title": "Finance Manager", "roles": ["FINANCE", "EMPLOYEE"], "clearance": 4},
    {"key": "legal_counsel", "title": "Legal Counsel", "roles": ["LEGAL", "EMPLOYEE"], "clearance": 4},
    {"key": "ciso", "title": "CISO", "roles": ["CISO", "SECURITY", "EMPLOYEE"], "clearance": 4},
    {"key": "strategist", "title": "Strategist", "roles": ["STRATEGY", "EMPLOYEE"], "clearance": 4},
    {"key": "cfo", "title": "CFO", "roles": ["C_SUITE", "FINANCE"], "clearance": 5},
    {"key": "ceo", "title": "CEO", "roles": ["C_SUITE", "BOARD"], "clearance": 5},
]

# The opaque legacy_mart view DDL (mirrors LEGACY_VIEWS) — mined into the glossary.
DEMO_LEGACY_VIEWS: dict[str, str] = {
    "v_cust": "SELECT text_1 AS customer_id, text_2 AS name, text_5 AS email FROM tbl_44",
    "v_orders": "SELECT text_1 AS order_id, num_7 AS total, text_2 AS status FROM tbl_71",
}

# The mined glossary mapping (deterministic result of mine_views(DEMO_LEGACY_VIEWS)) —
# baked static so /glossary works in the lean container without sqlglot. The headline:
# tbl_44.text_2 = "name" but tbl_71.text_2 = "status" (per-table disambiguation).
DEMO_GLOSSARY: list[dict] = [
    {"table": "tbl_44", "physical": "text_1", "means": "customer_id", "confidence": "high"},
    {"table": "tbl_44", "physical": "text_2", "means": "name", "confidence": "high"},
    {"table": "tbl_44", "physical": "text_5", "means": "email", "confidence": "high"},
    {"table": "tbl_71", "physical": "num_7", "means": "total", "confidence": "high"},
    {"table": "tbl_71", "physical": "text_1", "means": "order_id", "confidence": "high"},
    {"table": "tbl_71", "physical": "text_2", "means": "status", "confidence": "high"},
]

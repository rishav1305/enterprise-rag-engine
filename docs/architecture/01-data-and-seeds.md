# 1 — Data & seeds (Meridian, the 15×14 matrix, the opaque legacy_mart)

> Source of truth: [`docs/meridian-org-and-data.md`](../meridian-org-and-data.md) (the "world bible").
> The build — connectors, catalog, personas, masking, synthetic generators, the leak-audit
> golden set — is generated **against** that document. Everything below cites it.

## Meridian — the demo org

**Meridian** ("the everything app for cities") — a global super-app + marketplace, ~**12,000
employees**, HQ New York. Four verticals: Mobility, Marketplace, Pay (fintech/KYC), Ads. The
data is deliberately a mess because Meridian **grew by acquisition** — `OldMart` (legacy
retailer → the **opaque-schema warehouse**), `FleetGo` (logistics), `PayBridge` (payments) —
never fully harmonized. CLEARANCE is the governed RAG layer over all of it.

## The clearance model (0–5) — level AND role

A `SecurityContext` (frozen Pydantic, `schemas.py`) carries `allowed_roles[]`,
`clearance_level (0–5)`, `owner_department`, `sensitivity_class`, `need_to_know_roles[]`. An
asset inherits the clearance of its source; a session carries the persona's roles + level.

**Access requires BOTH sufficient level AND role/need-to-know** — high level ≠ see-everything.
This non-monotonicity is what makes the leak audit meaningful.

## The 15 personas (the demo roster)

Intern (L1, the adversarial-leak protagonist) · Support Agent (L2) · Data Analyst (L2, the
text-to-SQL user) · Ops Analyst (L2) · Commerce Analyst (L2) · Marketing Analyst (L2) ·
Engineer (L2, the lexical user) · HR Analyst (L4) · Sales Manager (L3) · Finance Manager (L4) ·
Legal Counsel (L4) · CISO (L4) · Strategist (L4) · CFO (L5) · CEO (L5).

The canonical persona definitions are emitted by `seeds/emit.py::build_oracle()["personas"]`
(title / level / roles) — the same source the demo's `/personas` endpoint and the leak oracle
both read, so there is no drift.

## The 14 sensitivity classes (A–N)

| Class | Meaning | Min level | Need-to-know roles |
|---|---|:--:|---|
| A | Public | 0 | open |
| B | Employee-general | 1 | open |
| C | Team-ops | 2 | open |
| D | Customer-PII | 3 | **masked** below L4 (raw at L4+) |
| E | Pre-release financials | 4 | FINANCE / C_SUITE |
| F | Exec comp | 5 | C_SUITE |
| G | Legal / M&A | 4 | LEGAL / STRATEGY / C_SUITE |
| H | Security incidents | 4 | CISO / SECURITY / BOARD |
| I | Payroll (individual) | 5 | HR / C_SUITE |
| J | Benefits (health PII) | 4 | HR / C_SUITE |
| K | Recruiting/ATS (candidate PII) | 3 | HR / C_SUITE |
| L | Expenses | 2 | FINANCE / C_SUITE |
| M | Tax (pre-filing) | 5 | FINANCE / C_SUITE |
| N | Treasury (material non-public) | 5 | FINANCE / C_SUITE |

The authoritative class table is `seeds/access_matrix.py::CLASSES` (`SensitivityClass` =
`code / name / min_level / need_to_know_roles`). The re-included function-specific classes
**I–N require the owning vertical's role**, not clearance alone (governance tightening
2026-06-09): an L2 analyst no longer reads benefits (J) or expenses (L) by level. The
engine's `governance.connector._CLASS_ROLES` is **derived from** `access_matrix.CLASSES` —
single source, no drift.

## The 15×14 access matrix = the 210-cell oracle

15 personas × 14 classes = **210 cells**, each with a ground-truth decision
(`allow` / `mask` / `partial` / `deny`). `seeds/emit.py::build_oracle()["expectations"]` is the
golden set; `seeds/access_matrix.py::evaluate_class(code, level, roles)` is the reference
decision. The leak oracle (deep dive [§3](03-governance.md)) asserts the engine's
`governance.access.evaluate` reproduces all 210 cells with **zero mismatch**.

**The teaching points (non-monotonic):**
- **Finance Manager** (L4) has high clearance but **cannot** see exec comp (F) or HR
  benefits/payroll (J/I — wrong function).
- **Legal** (L4) **cannot** see financials (E) or comp (F).
- **HR Analyst** (L4) sees benefits/recruiting (J/K) but **not** exec comp (F, L5).
- **Customer-PII (class D) is masked, not raw, below L4** — including for Sales Manager (L3):
  the row is still returned, with PII redacted (least-privilege). Pinned by
  `tests/test_leak_oracle.py::test_sales_manager_customer_pii_is_masked_not_raw`.

## Data estate

- **Real public sources** (the PB tail, query-in-place): e.g. NYC-TLC trips, GDELT events —
  queried via BigQuery text-to-SQL, **never bulk-ingested** (world bible §6).
- **Synthetic sources** (16 total, world bible §7): CRM, financials, payroll, benefits,
  recruiting/ATS, expenses, tax, treasury, security incidents, support, tickets, etc.
  (`seeds/synthetic/*.py`, each a `generate(manifest)` emitting a `SourceOutput` with a
  `CatalogAsset` + rows). Re-included per the robust/no-YAGNI directive — they add breadth +
  more sensitive governance surface (bank/health PII, pre-release tax/treasury at L5).

## The opaque-schema legacy warehouse (the glossary showcase)

`OldMart`'s warehouse (`seeds/synthetic/legacy_mart.py`) has **meaningless column names**:
`tbl_44.text_2` is the customer full name, `tbl_71.text_2` is an order status — the **same
physical name means different things per table**. `GLOSSARY_TRUTH` maps physical→meaning;
`LEGACY_VIEWS` (`v_cust AS SELECT text_2 AS name FROM tbl_44`) are the documentation evidence
the glossary miner reads. This is the engine the opaque-schema glossary (deep dive
[§7](07-glossary.md)) resolves: a question about "customer name" → `(tbl_44, text_2)`.

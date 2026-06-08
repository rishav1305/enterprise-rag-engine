# Meridian — Org & Data Reference ("the world bible")

**Reference doc** · 2026-06-08 · project `enterprise-rag-engine` (CLEARANCE / P0)

> The canonical description of the demo org, its people, and its complete data estate (real + synthetic). The build (connectors, catalog, personas, masking policies, synthetic-data generators, and the leak-audit golden set) is generated **against this document**. Architecture lives in `docs/superpowers/specs/2026-06-08-clearance-polystore-design.md` §3.5; this is the detailed expansion.

---

## 1. The company

**Meridian** — *"the everything app for cities."* A global super-app + marketplace, founded 2014, ~**12,000 employees**, HQ in New York with regional hubs in London, Singapore, and São Paulo.

**Business lines:**
- **Meridian Mobility** — ride-hailing + last-mile logistics/delivery.
- **Meridian Marketplace** — online retail/commerce (first-party + third-party merchants).
- **Meridian Pay** — fintech: wallet, payments, KYC.
- **Meridian Ads** — growth/advertising across the app.
- **Corporate / Strategy** — finance, people, legal, security, M&A.

**Why the data is a mess (the premise):** Meridian grew by **acquisition** — `OldMart` (legacy retailer, acq. 2019 → the **opaque-schema warehouse**), `FleetGo` (logistics, acq. 2020), `PayBridge` (payments, acq. 2022). Each came with its own systems, schemas, and conventions that were never fully harmonized. The result: petabytes spread across a warehouse with meaningless column names, a data lake of trips and logs, billions of external-signal records too big to ingest, and sensitive corporate documents scattered across a dozen SaaS tools. **CLEARANCE is the governed RAG layer over all of it.**

---

## 2. Clearance model (0–5)

A `SecurityContext` (frozen Pydantic model in the engine) carries `allowed_roles[]`, `clearance_level (0–5)`, `owner_department`. An asset inherits the clearance of its source; a session carries the persona's roles + level. Access requires **both** sufficient level **and** role/need-to-know (so high level ≠ see-everything — see §5).

| Level | Name | Who | Example data |
|---|---|---|---|
| **L0** | PUBLIC | anyone, incl. external | SEC filings, published help docs, open gov data |
| **L1** | EMPLOYEE | any Meridian employee | policies, internal wiki, aggregate metrics |
| **L2** | TEAM / MANAGER | team members | team-scoped ops: trips, sales, tickets, campaigns |
| **L3** | DIRECTOR | cross-team leads | raw customer records, contract terms, deal values |
| **L4** | VP / EXEC-STAFF | function heads | financials, KYC PII, security incidents, legal |
| **L5** | BOARD / C-SUITE | C-suite + board | **pre-release financials, exec comp, M&A** |

---

## 3. Org structure (verticals)

| # | Vertical | Mission | Primary systems | Data it owns |
|---|---|---|---|---|
| 1 | **Finance** | revenue, planning, reporting | Warehouse, Drive | revenue-by-segment, **pre-release financials (L5)**, SEC filings (L0) |
| 2 | **People / HR** | hiring, comp, performance | Workday (HRIS) | headcount, comp bands, **exec comp (L5)**, HR policies (L1) |
| 3 | **Sales** | merchant + enterprise deals | Salesforce (CRM) | pipeline, accounts, contracts, **deal value (field-level secured)** |
| 4 | **Legal & Compliance** | contracts, M&A, litigation | Drive, Confluence | contracts (L3), **M&A + litigation (L5)** |
| 5 | **Engineering / Data Platform** | builds + runs the platform | Confluence, Jira, the warehouse | runbooks, architecture docs, **prod creds (masked)** |
| 6 | **Mobility Ops** | ride-hail + logistics ops | Data lake | **trip records (PII coords masked)**, driver/rider data |
| 7 | **Marketplace / Commerce** | retail + merchant ops | Warehouse | sales transactions, merchant data, **customer email (masked)** |
| 8 | **Marketing / Growth** | campaigns, ads, signals | Ads tools, data-share | campaign + ad-spend data, market/event signals |
| 9 | **Risk & Security** | fraud, threat, audit | SIEM, Jira | incidents, threat intel, **audit logs (L4)** |
| 10 | **Strategy / Intelligence** | competitive intel, M&A | Drive, data-share | competitor filings, **M&A targets (L5)** |
| 11 | **Knowledge / Support** | help content, support | Confluence, Zendesk, Slack | internal wiki (L1), support tickets (customer PII masked) |

---

## 4. Personas (the demo roster)

| Persona | Vertical | Level | Notes |
|---|---|---|---|
| **Intern** | Knowledge/Support | L1 | the adversarial-leak protagonist |
| **Support Agent** | Knowledge/Support | L1 | customer-facing; sees masked PII |
| **Data Analyst** | Engineering/Data | L2 | queries the warehouse; the text-to-SQL user |
| **Ops Analyst** | Mobility Ops | L2 | trip aggregates |
| **Commerce Analyst** | Marketplace | L2 | sales analytics |
| **Marketing Analyst** | Marketing | L2 | campaign data; masked customer emails |
| **Engineer** | Engineering | L2 | runbooks, tickets, error codes (lexical user) |
| **Sales Manager** | Sales | L3 | pipeline, deal values |
| **Finance Manager** | Finance | L4 | financials — **not** comp |
| **Legal Counsel** | Legal | L4 | contracts, M&A — **not** financials/comp |
| **CISO** | Risk & Security | L4 | security incidents, audit logs |
| **Strategist** | Strategy/Intelligence | L4 | competitive intel + **M&A targets** — allowed G where Sales is denied (golden scenario #6) |
| **CFO** | Finance / C-suite | L5 | financials **and** comp **and** M&A |
| **CEO** | C-suite | L5 | everything |

---

## 5. Access matrix (the governance core — deliberately non-monotonic)

Asset sensitivity classes: **A** Public (L0) · **B** Employee-general (L1) · **C** Team-ops (L2) · **D** Customer-PII (L3, masked below L4) · **E** Pre-release financials (**L4+, FINANCE/C-suite need-to-know**) · **F** Exec comp (L5) · **G** Legal/M&A (L4–L5) · **H** Security incidents (L4).

| Persona | A | B | C | D | E | F | G | H |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Intern | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Support Agent | ✓ | ✓ | own queue | **masked** | ✗ | ✗ | ✗ | ✗ |
| Data/Ops/Commerce Analyst | ✓ | ✓ | ✓ | **masked** | ✗ | ✗ | ✗ | ✗ |
| Marketing Analyst | ✓ | ✓ | ✓ | **masked** | ✗ | ✗ | ✗ | ✗ |
| Engineer | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | partial |
| Sales Manager | ✓ | ✓ | ✓ | **masked** | ✗ | ✗ | ✗ | ✗ |
| Finance Manager | ✓ | ✓ | ✓ | ✓ | ✓ | **✗** | ✗ | ✗ |
| Legal Counsel | ✓ | ✓ | ✓ | ✓ | **✗** | **✗** | ✓ | ✗ |
| Strategist | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | **✓** | ✗ |
| CISO | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ |
| CFO | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| CEO | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

**The point:** Finance Manager has high clearance but **cannot** see exec comp (F); Legal has high clearance but **cannot** see financials (E) or comp (F); HR can see comp bands but not pre-release financials. Access = **level AND role/need-to-know**, never level alone. This is what makes the leak audit meaningful.

> **Customer-PII (class D) is masked, not raw, below L4 — including for Sales Manager (L3).** Earlier drafts gave Sales Manager raw D; the implementation masks it (least-privilege/SECURE pillar): the row is still returned, with PII redacted. Raw customer PII requires L4+. Pinned by `tests/test_leak_oracle.py::test_sales_manager_customer_pii_is_masked_not_raw`.

---

## 6. Data estate — real public sources

| Asset | Real source (link) | Connector | Vertical | Retrieval mode | Scale | Sensitivity / masking |
|---|---|---|---|---|---|---|
| Marketplace transactions | **TPC-DS** `store_sales` ([spec](https://www.tpc.org/tpcds/)) | Warehouse (BigQuery) | Commerce/Finance | Structured / text-to-SQL | up to 10 TB | `customer_email` masked; raw L3, aggregates L1 |
| Mobility trips | **NYC TLC** ([BigQuery public](https://console.cloud.google.com/marketplace/details/city-of-new-york/nyc-tlc-trips)) | Data lake | Mobility Ops | Structured / text-to-SQL | ~1.6B rows | pickup/dropoff coords masked (PII); aggregates L1 |
| Global events / risk signals | **GDELT** ([gdelt-bq](https://www.gdeltproject.org/)) | Data-share | Strategy/Marketing | Structured + vector | billions, 15-min | L1 |
| Web / competitor corpus | **Common Crawl** ([commoncrawl.org](https://commoncrawl.org/)) | S3 object store | Strategy | catalog-only (PB tail) | PB | L1 |
| Company filings | **SEC EDGAR** ([edgar](https://www.sec.gov/edgar)) | Files / API | Strategy/Legal | Vector + lexical | ~16M filings | public L0 |
| Open city/economic data | **data.gov** ([data.gov](https://data.gov/)) | Files / API | Ops/Marketing | Structured | varies | public L0 |
| Internal knowledge base | **Wikipedia/Wikimedia** ([dumps](https://dumps.wikimedia.org/)) | Confluence/wiki | Knowledge | **Vector (primary)** | ~6.8M articles | L0–L1 |

---

## 7. Data estate — synthetic sources

All synthetic data is **clearly labeled** in the UI and **deterministically generated** (seeded) so the leak audit is reproducible. Generation tooling: `Faker` + seeded `numpy`/`Polars`, with some tables **derived from the public aggregates** (e.g., pre-release financials roll up from TPC-DS sales) so the numbers cohere.

| Asset | Connector | Vertical | Retrieval mode | Approx volume | Key fields / shape | Sensitivity / masking |
|---|---|---|---|---|---|---|
| HR records + **exec comp** | HRIS (Workday) | People | Vector + structured | ~12k employees; ~120 execs | employee_id, dept, band, salary, manager_id | comp **L5**; policies/bands L1 |
| CRM pipeline | CRM (Salesforce) | Sales | Structured + vector | ~30k opportunities | account, stage, **deal_value (field-level secured)**, owner | deal value L3; field-level security |
| Internal comms | Messages (Slack) | all | Vector + lexical | ~200k messages | channel, user, ts, text | **channel-scoped** ACLs |
| **Pre-release financials** | Drive / warehouse | Finance | Vector + structured | ~8 quarters × segments | segment, quarter, projection, status=draft | **L5** until release |
| **M&A / litigation memos** | Drive | Legal | Vector | ~150 docs | target, thesis, status, counsel notes | **L5** |
| **Procurement / supplier graph** | ERP / procurement | Ops/Legal | **Graph (primary)** | ~2k suppliers, ~8k contracts, ~15k components, ~300 recalls | supplier→contract→component→recall edges | supplier list L1; contract terms L3 |
| **Eng/IT incident tickets + error codes** | Jira/ServiceNow + Confluence | Engineering/Security | **Lexical (primary)** | ~50k tickets, ~2k error codes, ~1k runbooks | ticket_id (MER-####), error_code (ERR-DB-0042), component, severity | L1–L2; security-incident tickets L3 |
| **Payments ledger + KYC** | Warehouse / payments DB | Finance/Risk | Structured + masking | ~5M transactions, ~200k KYC identities | txn_id, amount, merchant, **kyc: name/dob/gov_id (masked)** | KYC PII **masked**, raw L4; aggregates L1 |
| **Customer support tickets + transcripts** | Zendesk / Slack | Support | Vector + lexical | ~30k tickets + transcripts | ticket_id, customer_ref, transcript, resolution | customer PII **masked**; L1 |
| **App/service telemetry logs** | Data lake | Engineering/Ops | **funnel tier-out** (mostly NOT indexed) | ~200M log lines | ts, service, level, trace_id, msg | L2; demonstrates dedup/tiering |
| **Payroll runs** | HRIS (Workday) | People | Structured + masking | ~12k employees × ~30 periods | employee_id, period, gross, net, deductions, **bank_acct (masked)** | **L5** (ties to comp); bank PII masked |
| **Benefits enrollments** | HRIS (Workday) | People | Structured + vector | ~12k employees | employee_id, plan, dependents, **health elections (masked)** | L4; health PII masked |
| **Recruiting / ATS** | ATS (Greenhouse) | People | Vector + structured | ~25k candidates, ~3k reqs | candidate, req, stage, **interview notes, comp ask** | L3; candidate PII masked; offers L4 |
| **Expenses / AP** | Finance (Concur/ERP) | Finance | Structured | ~150k expense lines | employee_id, vendor, amount, category, receipt_ref | L2; aggregates L1 |
| **Tax filings / provisions** | Finance / Drive | Finance | Vector + structured | ~8 quarters × jurisdictions | jurisdiction, period, provision, status=draft | **L5** (pre-release) |
| **Treasury / cash positions** | Finance / warehouse | Finance | Structured | ~daily × accounts | account, balance, currency, counterparty | **L5** |

**Re-included per the robust/no-YAGNI directive** (memory `clearance-build-philosophy-robust`): payroll, benefits, recruiting/ATS, expenses, tax, treasury — they add breadth + more sensitive governance surface (bank/health PII, pre-release tax/treasury at L5). Total synthetic sources: **16**.

---

## 8. The opaque-schema legacy warehouse (the glossary showcase)

The acquired **OldMart** retailer's warehouse (`legacy_mart` schema) was never harmonized — column and table names carry **no semantic signal**. This is the dataset the **opaque-schema semantic glossary** subsystem reverse-engineers. Illustrative seed:

| Physical | Means (glossary target) | Evidence the miner uses |
|---|---|---|
| `tbl_44` | customers | FK fan-in; a legacy view `v_cust AS SELECT text_2 AS name FROM tbl_44` |
| `tbl_44.text_1` | customer_id | high cardinality, PK, UUID-like values |
| `tbl_44.text_2` | full name | two-token strings, name patterns |
| `tbl_44.text_5` | email | regex match on `@` |
| `tbl_44.num_3` | loyalty tier | low cardinality {1,2,3} |
| `tbl_71` | orders | FK→tbl_44; dated rows |
| `tbl_71.num_7` | order total | currency distribution |
| `tbl_71.text_2` | order status | enum {placed,shipped,returned} |

The glossary subsystem (`enrichment/schema_glossary/`) **profiles values** + **mines legacy views/BI/dbt** + **LLM-drafts** (Groq/NVIDIA) + **human-approves** → text-to-SQL retrieves over the **glossary**, never the raw schema, so it writes `SELECT text_2 FROM tbl_44` correctly. Low-confidence inferences are flagged until validated; CI flags schema drift.

---

## 9. Governance golden scenarios (the leak-audit set)

Each is a `(persona, query) → expected behaviour` case the adversarial CI gate asserts. **0 leaks** required.

| # | Persona | Query | Expected |
|---|---|---|---|
| 1 | **Intern** | "What are our Q3 financial projections and exec salary structures?" | **DROP** pre-release financials (E) + exec comp (F); answer only from public/employee content + audit trail of drops |
| 2 | **CFO** | (same) | **ALLOW** E + F — same index, different session token |
| 3 | **HR Analyst** | "Show the executive team's compensation" | **DROP** exec comp (F, L5); general comp bands allowed |
| 4 | **Finance Manager** | "List individual employee salaries" | **DENY** — high clearance but comp is out of Finance's need-to-know (level alone ≠ access) |
| 5 | **Marketing Analyst** | "Give me customer emails for the campaign" | **MASKED** — emails returned redacted (PII masking), not blocked |
| 6 | **Strategist** | "Which companies are M&A targets?" | **ALLOW** (L4 Strategy); the same query as **Sales Manager** → **DENY** |
| 7 | **Engineer** | "What's error code ERR-DB-0042?" | **ALLOW** via lexical/full-text exact-ID match (showcases the lexical leg) |
| 8 | **Ops Analyst** | "Average trip fare by borough last quarter" | **ALLOW** aggregate; raw pickup coords remain **masked** |

---

## 10. Synthetic-data generation plan (for the build)

- **Deterministic + seeded** (`SEED` in config) so the leak audit is reproducible.
- **Coherence:** pre-release financials are **rolled up from TPC-DS sales aggregates**; payments amounts tie to marketplace orders; org chart (manager_id) is internally consistent for the graph/HR scenarios.
- **PII is realistic but fake** (Faker) and **always masked at the governance layer** for unauthorized roles — never just absent.
- **Volumes** are demo-right (table in §7), not production — the *funnel math + provenance badges* tell the petabyte story; telemetry logs are generated large precisely to be tiered/deduped out.
- **Labeling:** every synthetic source carries a `synthetic: true` flag surfaced in the UI; every real source carries a provenance link + scale badge.

Generators will live in `seeds/` (per-source modules) and write into SurrealDB Cloud + the TurboVec index via the offline build pipeline (spec §3.4).

---

*Status 2026-06-08: org + full data estate documented (11 verticals, **14 personas** incl. Strategist, 7 real sources, **16 synthetic sources**, opaque-schema seed, access matrix, 8 golden leak-audit scenarios). Drives the catalog, connectors, masking policies, and synthetic generators. Build owned by Shuri; P0.1a in execution.*

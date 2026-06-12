"""Estate assembler (G1) — the full data estate (31 sources) for the Datasets tab.

build_estate() returns 31 sources: 6 LIVE demo docs (the indexed corpus) + 7 real
PB-tail public sources + 18 synthetic estate sources.

Runtime-safe STATIC data (mirrors `seeds/real/sources.py` + the synthetic source
metadata + the live demo docs) — NO `seeds` import (that pulls heavy seed-gen deps at
runtime, the P0.11c lesson). ``live_queryable`` flags the docs actually indexed in the
demo (the 6 corpus docs incl. the 2 G0 PII/partial docs); the rest are catalog-only
(the PB-tail story: catalogued + governed, queried-in-place, never bulk-ingested).

Read-only METADATA only — name/type/scale/class/clearance/provenance/live_queryable.
NO row data ever.
"""

from __future__ import annotations

# (name, type, scale_badge, sensitivity_class, clearance_level, provenance_url, live)
_REAL = [
    ("Marketplace transactions (TPC-DS)", "warehouse", "up to 10 TB", "C", 2,
     "https://www.tpc.org/tpcds/", False),
    ("Mobility trips (NYC-TLC)", "warehouse", "≈1.6B rows · ~400 GB", "C", 2,
     "https://console.cloud.google.com/marketplace/details/city-of-new-york/nyc-tlc-trips", False),
    ("Global events / risk signals (GDELT)", "stream", "billions · 15-min cadence", "B", 1,
     "https://www.gdeltproject.org/", False),
    ("Web / competitor corpus (Common Crawl)", "lake", "PB-scale (catalog-only)", "B", 1,
     "https://commoncrawl.org/", False),
    ("Company filings (SEC EDGAR)", "docs", "≈16M filings", "A", 0,
     "https://www.sec.gov/edgar", False),
    ("Open city/economic data (data.gov)", "warehouse", "varies", "A", 0,
     "https://data.gov/", False),
    ("Internal knowledge base (Wikipedia dump)", "vector", "≈6.8M articles", "B", 1,
     "https://dumps.wikimedia.org/", False),
]

_SYNTHETIC = [
    ("CRM pipeline", "structured", "≈30k opportunities", "C", 2),
    ("Pre-release financials", "structured", "≈8 quarters × segments", "E", 4),
    ("HR records + exec comp", "docs", "≈12k employees · ~120 execs", "F", 5),
    ("OldMart legacy warehouse (tbl_44, opaque schema)", "structured",
     "≈5k customers (opaque schema)", "D", 3),
    ("M&A / litigation memos", "docs", "≈150 docs", "G", 4),
    ("Payments ledger + KYC", "structured", "≈5M transactions · 200k KYC identities", "D", 4),
    ("Payroll runs", "structured", "≈12k employees × monthly", "I", 5),
    ("Procurement / supplier graph", "graph",
     "≈2k suppliers · 8k contracts · 15k components", "C", 2),
    ("Recruiting / ATS", "structured", "≈4k reqs × candidates", "K", 3),
    ("Security incidents + threat intel", "docs", "≈1.2k incidents", "H", 4),
    ("Internal comms (Slack)", "lexical", "≈200k messages", "C", 2),
    ("Customer support tickets + transcripts", "lexical", "≈30k tickets", "D", 1),
    ("Corporate tax filings/provisions", "structured", "≈8 quarters × jurisdictions", "M", 5),
    ("App/service telemetry logs", "lexical", "≈800M lines (tiered/deduped)", "C", 2),
    ("Eng/IT incident tickets + error codes", "lexical", "≈50k tickets · ~2k error codes", "C", 2),
    ("Benefits enrollment", "structured", "≈12k employees", "J", 4),
    ("Expense reports", "structured", "≈40k reports", "L", 2),
    ("Treasury — cash/FX/debt", "structured", "≈8 quarters × instruments", "N", 5),
]

# the LIVE demo docs (actually indexed in the corpus — live_queryable=True).
_LIVE_DEMO = [
    ("Remote Work Policy 2026", "docs", "1 policy doc", "A", 0, "", True),
    ("Product Pricing (public)", "docs", "1 pricing doc", "A", 0, "", True),
    ("Executive Compensation Schedule 2026", "docs", "1 restricted doc", "F", 5, "", True),
    ("Q3 Financials (pre-release)", "docs", "1 restricted doc", "E", 4, "", True),
    ("Customer Account Record (PII sample)", "docs", "1 class-D PII record", "D", 3, "", True),
    ("Engineering On-Call Incident (dept-scoped)", "docs", "1 partial-scope record", "G", 2, "", True),
]


def build_estate() -> dict:
    sources: list[dict] = []
    for name, typ, badge, cls, lvl, prov, live in _LIVE_DEMO:
        sources.append({"name": name, "type": typ, "scale_badge": badge,
                        "sensitivity_class": cls, "clearance_level": lvl,
                        "provenance_url": prov, "live_queryable": live, "synthetic": True})
    for name, typ, badge, cls, lvl, prov, live in _REAL:
        sources.append({"name": name, "type": typ, "scale_badge": badge,
                        "sensitivity_class": cls, "clearance_level": lvl,
                        "provenance_url": prov, "live_queryable": live, "synthetic": False})
    for name, typ, badge, cls, lvl in _SYNTHETIC:
        sources.append({"name": name, "type": typ, "scale_badge": badge,
                        "sensitivity_class": cls, "clearance_level": lvl,
                        "provenance_url": "", "live_queryable": False, "synthetic": True})
    return {"sources": sources}


__all__ = ["build_estate"]

"""P0.11b B2/B4/B5 — GATE A: read-only metadata endpoints carry NO restricted content.

/personas (switcher options), /glossary (opaque-schema mapping), /funnel (scale viz).
Each is enumerated in the Gate A checklist; each is read-only and must expose only
metadata — never governed row content.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import re

# the structural key-set assertions carry the real weight (a row-content field would
# change the key set); this currency/PII-shape scan is belt-and-suspenders: NO
# dollar-amount-shaped value should appear in a metadata endpoint (those are row data).
RESTRICTED = "$480,000"          # one known restricted literal (kept for clarity)
_CURRENCY = re.compile(r"\$\s?\d[\d,]{3,}")   # $1,234+ shaped -> row-data smell


def _no_currency_values(text: str) -> bool:
    return _CURRENCY.search(text) is None


@pytest.fixture(scope="module")
def client():
    from rag_engine.api import app
    with TestClient(app) as c:
        yield c


def test_personas_lists_switcher_options_no_content(client):
    r = client.get("/personas")
    assert r.status_code == 200
    data = r.json()["personas"]
    assert any(p["key"] == "intern" for p in data)
    # each entry is metadata only (title/roles/clearance) — no answer/content fields.
    for p in data:
        assert set(p.keys()) == {"key", "title", "roles", "clearance"}
    assert RESTRICTED not in r.text


def test_glossary_exposes_mapping_only_not_row_data(client):
    r = client.get("/glossary")
    assert r.status_code == 200
    entries = r.json()["glossary"]
    # the headline mapping: tbl_44.text_2 -> the customer name meaning.
    name_entry = next((e for e in entries
                       if e["table"] == "tbl_44" and e["physical"] == "text_2"), None)
    assert name_entry is not None and name_entry["means"] in ("name", "full_name")
    # mapping fields ONLY — no example values / row data.
    for e in entries:
        assert set(e.keys()) == {"table", "physical", "means", "confidence"}
    assert RESTRICTED not in r.text


def test_funnel_is_scale_metadata_only(client):
    r = client.get("/funnel")
    assert r.status_code == 200
    funnel = r.json()["funnel"]
    assert isinstance(funnel, list) and funnel, "funnel should return stage rows"
    # STRUCTURAL key-set assertion: each stage row carries ONLY scale/collapse metadata
    # fields — an injected row-content field changes the key set and BITES (the prior
    # isinstance-only test was hollow).
    allowed = {"stage", "count", "bytes", "note", "provenance_url"}
    for row in funnel:
        assert set(row.keys()) <= allowed, f"unexpected funnel field(s): {set(row) - allowed}"
    # the funnel shows the PB-tail scale collapse -> the top-k reaching the model.
    assert any("pb_tail" in (row.get("stage") or "") for row in funnel)
    assert any(row.get("stage") == "final_top_k" for row in funnel)
    assert RESTRICTED not in r.text


def test_metadata_endpoints_need_no_auth_but_leak_nothing(client):
    # these are public (no headers) — and still carry no restricted content and NO
    # currency/row-data-shaped value (the structural smell, not just one literal).
    for path in ("/personas", "/glossary", "/funnel"):
        r = client.get(path)
        assert r.status_code == 200
        assert RESTRICTED not in r.text
        assert _no_currency_values(r.text), f"{path} exposes a currency-shaped value"

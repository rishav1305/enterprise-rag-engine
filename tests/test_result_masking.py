"""P0.3b WORKER-A — exhaustive result_masking.mask_rows cases."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.catalog.asset import ColumnPolicy  # noqa: E402
from rag_engine.texttosql.result_masking import mask_rows  # noqa: E402

_PII = ColumnPolicy(name="customer_email", pii=True, masked=True, mask_reason="PII_MASK")
_ACL = ColumnPolicy(name="deal_value", pii=False, masked=True, mask_reason="FIELD_ACL_MASK")
_OPEN = ColumnPolicy(name="fare", pii=False, masked=False)


def test_pii_column_redacted():
    out = mask_rows([{"customer_email": "x@y.com", "fare": 1.0}], (_PII, _OPEN), mask=True)
    assert out[0]["customer_email"] == "[REDACTED]"
    assert out[0]["fare"] == 1.0


def test_field_acl_column_uses_restricted_token():
    out = mask_rows([{"deal_value": 125000}], (_ACL,), mask=True)
    assert out[0]["deal_value"] == "[RESTRICTED]"


def test_passthrough_when_mask_false():
    out = mask_rows([{"customer_email": "x@y.com"}], (_PII,), mask=False)
    assert out[0]["customer_email"] == "x@y.com"


def test_multi_row_all_masked():
    rows = [{"customer_email": f"u{i}@y.com"} for i in range(5)]
    out = mask_rows(rows, (_PII,), mask=True)
    assert all(r["customer_email"] == "[REDACTED]" for r in out)
    assert "u3@y.com" not in str(out)


def test_empty_rows_returns_empty():
    assert mask_rows([], (_PII,), mask=True) == []


def test_no_masked_columns_passthrough():
    out = mask_rows([{"fare": 9.0}], (_OPEN,), mask=True)
    assert out[0]["fare"] == 9.0


def test_does_not_mutate_caller_rows():
    rows = [{"customer_email": "x@y.com"}]
    mask_rows(rows, (_PII,), mask=True)
    assert rows[0]["customer_email"] == "x@y.com"   # original untouched (copy-not-mutate)


def test_unknown_mask_reason_falls_back_to_pii_redaction():
    weird = ColumnPolicy(name="c", pii=True, masked=True, mask_reason="NONSENSE")
    out = mask_rows([{"c": "secret"}], (weird,), mask=True)
    assert out[0]["c"] == "[REDACTED]"              # fail-closed (never raw)
    assert "secret" not in str(out)


def test_missing_column_in_row_is_ignored():
    # a masked column declared but absent from a given row -> no error
    out = mask_rows([{"fare": 1.0}], (_PII, _OPEN), mask=True)
    assert out[0] == {"fare": 1.0}

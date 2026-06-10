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


# ---- CRITICAL-fix: AST-source-driven masking (alias/case/expr/* bypasses) -----
from rag_engine.sql.ast_gate import assert_read_only, projection_sources  # noqa: E402

_VICTIM = "victim@pii.com"


def _projs(sql):
    return projection_sources(assert_read_only(sql))


def test_alias_bypass_is_masked():
    p = _projs("SELECT customer_email AS em FROM t WHERE d>='2024-01-01'")
    out = mask_rows([{"em": _VICTIM}], (_PII,), mask=True, projections=p)
    assert out[0]["em"] == "[REDACTED]" and _VICTIM not in str(out)


def test_case_variant_key_is_masked():
    p = _projs("SELECT customer_email FROM t WHERE d>='2024-01-01'")
    out = mask_rows([{"CUSTOMER_EMAIL": _VICTIM}], (_PII,), mask=True, projections=p)
    assert out[0]["CUSTOMER_EMAIL"] == "[REDACTED]" and _VICTIM not in str(out)


def test_expression_over_masked_column_is_masked():
    for sql, key in [
        ("SELECT UPPER(customer_email) AS u FROM t WHERE d>='2024-01-01'", "u"),
        ("SELECT customer_email || 'x' AS c FROM t WHERE d>='2024-01-01'", "c"),
        ("SELECT SUBSTR(customer_email,1,3) AS s FROM t WHERE d>='2024-01-01'", "s"),
    ]:
        p = _projs(sql)
        out = mask_rows([{key: _VICTIM}], (_PII,), mask=True, projections=p)
        assert out[0][key] == "[REDACTED]", f"{sql} leaked"
        assert _VICTIM not in str(out)


def test_select_star_masks_the_masked_column():
    p = _projs("SELECT * FROM t WHERE d>='2024-01-01'")
    out = mask_rows([{"customer_email": _VICTIM, "fare": 1.0}], (_PII,),
                    mask=True, projections=p)
    assert out[0]["customer_email"] == "[REDACTED]"
    assert out[0]["fare"] == 1.0 and _VICTIM not in str(out)


def test_unresolvable_projection_fails_closed():
    # a projection whose source can't be tied to a base column -> REDACT (fail-closed)
    p = _projs("SELECT 'literal-or-opaque' AS mystery FROM t WHERE d>='2024-01-01'")
    out = mask_rows([{"mystery": "could-be-sensitive"}], (_PII,),
                    mask=True, projections=p)
    assert out[0]["mystery"] == "[REDACTED]"   # never assume safe


def test_masked_cell_non_string_value_redacted():
    # a masked cell holding a non-string (None, dict, number) is still redacted to
    # the token — mask_value replaces the value regardless of type (no AttributeError).
    for val in (None, {"nested": "x"}, 12345, [1, 2]):
        out = mask_rows([{"customer_email": val}], (_PII,), mask=True)
        assert out[0]["customer_email"] == "[REDACTED]"
        assert str(val) not in str(out) or val is None

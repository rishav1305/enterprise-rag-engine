"""CI quality gate. Returns non-zero exit semantics when thresholds are breached.

Wire into ``.github/workflows/ci.yml`` so a PR that drops recall or — far worse
— leaks a restricted document cannot merge.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GateThresholds:
    min_context_recall: float = 0.80
    min_context_precision: float = 0.40
    max_leak_rate: float = 0.0  # zero tolerance for governance leaks


@dataclass(slots=True)
class GateResult:
    passed: bool
    context_recall: float
    context_precision: float
    leak_rate: float
    messages: list[str]


def evaluate_gate(
    context_recall: float,
    context_precision: float,
    leak_rate: float,
    thresholds: GateThresholds | None = None,
) -> GateResult:
    t = thresholds or GateThresholds()
    msgs: list[str] = []
    ok = True
    if context_recall < t.min_context_recall:
        ok = False
        msgs.append(f"context_recall {context_recall:.2f} < {t.min_context_recall:.2f}")
    if context_precision < t.min_context_precision:
        ok = False
        msgs.append(f"context_precision {context_precision:.2f} < {t.min_context_precision:.2f}")
    if leak_rate > t.max_leak_rate:
        ok = False
        msgs.append(f"GOVERNANCE LEAK: leak_rate {leak_rate:.2f} > {t.max_leak_rate:.2f}")
    if ok:
        msgs.append("all gates passed")
    return GateResult(ok, context_recall, context_precision, leak_rate, msgs)

"""The governance core — sensitivity classes + the non-monotonic access matrix.

World bible §5 defines classes A..H; the re-included domains (payroll, benefits,
recruiting, expenses, tax, treasury) extend it with classes I..N per the P0.1a
plan. The matrix is deliberately NON-MONOTONIC: a high clearance level does not
imply access — Finance Manager (L4) cannot see exec comp; Legal (L4) cannot see
financials. Access = level AND role/need-to-know.

The expected-decision values here are what the leak-audit oracle (P0.1b) asserts.
``ALLOW`` = visible; ``MASK`` = returned redacted (PII), never blocked;
``DENY`` = dropped before the model + audited.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    ALLOW = "allow"
    MASK = "mask"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class SensitivityClass:
    code: str
    name: str
    min_level: int
    # roles that satisfy need-to-know; empty tuple = level-only (any role at level)
    need_to_know_roles: tuple[str, ...] = ()


# §5 classes A..H + re-included domains I..N
CLASSES: dict[str, SensitivityClass] = {
    "A": SensitivityClass("A", "Public", 0),
    "B": SensitivityClass("B", "Employee-general", 1),
    "C": SensitivityClass("C", "Team-ops", 2),
    "D": SensitivityClass("D", "Customer-PII", 3),  # masked below L4
    "E": SensitivityClass("E", "Pre-release financials", 5, ("FINANCE", "C_SUITE")),
    "F": SensitivityClass("F", "Exec comp", 5, ("C_SUITE",)),
    "G": SensitivityClass("G", "Legal/M&A", 4, ("LEGAL", "C_SUITE", "STRATEGY")),
    "H": SensitivityClass("H", "Security incidents", 4, ("CISO", "SECURITY")),
    # re-included domains (P0.1a expanded scope)
    "I": SensitivityClass("I", "Payroll (individual)", 5, ("FINANCE", "C_SUITE")),
    "J": SensitivityClass("J", "Benefits (PII)", 2),
    "K": SensitivityClass("K", "Recruiting/ATS (candidate PII; offer comp L4)", 3),
    "L": SensitivityClass("L", "Expenses", 2),
    "M": SensitivityClass("M", "Tax (pre-filing)", 5, ("FINANCE", "C_SUITE")),
    "N": SensitivityClass("N", "Treasury (material non-public)", 5, ("FINANCE", "C_SUITE")),
}


def evaluate_class(class_code: str, level: int, roles: tuple[str, ...]) -> Decision:
    """Reference governance decision for a persona vs a sensitivity class.

    This is the oracle's ground truth. ``D`` (customer PII) is the masking
    leg: visible-but-masked for analysts (L2–L3), raw at L4+.
    """
    sc = CLASSES[class_code]
    role_set = {r.upper() for r in roles}

    # masking leg for customer PII
    if class_code == "D":
        if level >= 4:
            return Decision.ALLOW
        if level >= 2:
            return Decision.MASK  # redacted, not blocked
        return Decision.DENY

    if level < sc.min_level:
        return Decision.DENY
    if sc.need_to_know_roles and not (role_set & set(sc.need_to_know_roles)):
        return Decision.DENY  # high level but wrong need-to-know -> non-monotonic
    return Decision.ALLOW

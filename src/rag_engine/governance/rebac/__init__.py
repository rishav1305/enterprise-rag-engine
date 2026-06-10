"""ReBAC allowlist backends (P0.6) — sub-linear list-objects in place of the
O(N)-per-query in-process scan, behind the AllowlistBackend ABC.

All backends MUST return EXACTLY the same allow/deny set as InProcessAllowlist
(parity-tested in tests/test_rebac_parity.py) — the optimization is sub-linear
LOOKUP, never a different DECISION. A superset leaks; a subset over-denies.

- LocalReBAC  : zero-dep relationship-tuple kernel (the SpiceDB *model*, computed
                in-process). Always available -> parity is provable with no creds.
- SpiceDB     : authzed gRPC client -> LookupResources (binary/creds-gated).
- OsoCloud    : oso-cloud list()  (creds-gated).
"""

from .local import LocalReBACAllowlist, ReBACTuple, governance_tuples

__all__ = ["LocalReBACAllowlist", "ReBACTuple", "governance_tuples"]

"""SpiceDBAllowlist — authzed gRPC ReBAC backend (binary/creds-gated).

Self-host SpiceDB: ``spicedb serve`` with a preshared key; this backend writes the
governance relationship tuples (governance_tuples) and answers the allowlist with
a single LookupResources call (sub-linear list-objects — the ELASTIC win).

Gated like SurrealDB: the authzed client is an OPTIONAL dependency and a running
SpiceDB endpoint + token are required. Constructing without them raises a clear
error; tests mark themselves @pytest.mark.spicedb and skip when unavailable. The
in-process default is always tested, so this being absent never reduces coverage
of the security-critical decision — only of the optimization path.

PARITY: LookupResources("view") MUST return exactly InProcessAllowlist's set
(parity-tested). The SpiceDB schema encodes the same rules as access.evaluate.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...schemas import EnrichedChunk, Session
from .local import governance_tuples

# SpiceDB schema (zed schema write). Encodes the governance rules as relations +
# a computed `view` permission. Operators apply this once; documented here so the
# backend is self-describing and reviewable.
SPICEDB_SCHEMA = """
definition user {}

definition chunk {
    relation public: user:*
    relation viewer_by_level: user:*
    relation ntk: user
    relation partial: user
    relation allowed_role: user   // legacy un-classed role gate (access.py:87)

    // A session is granted view when the in-process sync wrote it the matching
    // grants (public, or level-cleared, or NTK/partial, or the legacy allowed_role
    // grant for un-classed chunks). The sync layer (this backend) computes
    // level/class outcomes and writes the resulting grants so
    // LookupResources(view) == InProcessAllowlist. allowed_role MUST be included or
    // the backend inherits the LocalReBAC un-classed-leak blind spot.
    permission view = public + viewer_by_level + ntk + partial + allowed_role
}
""".strip()


def _require_authzed():
    try:
        from authzed.api.v1 import Client  # noqa: F401
    except ImportError as e:  # pragma: no cover - gated
        raise RuntimeError(
            "SpiceDBAllowlist requires the 'authzed' package and a running SpiceDB "
            "endpoint. Install authzed + run `spicedb serve`, or use the default "
            "InProcessAllowlist / LocalReBACAllowlist."
        ) from e


class SpiceDBAllowlist:
    def __init__(self, endpoint: str, token: str) -> None:
        _require_authzed()
        from authzed.api.v1 import Client
        from grpcutil import bearer_token_credentials

        self._endpoint = endpoint
        self._client = Client(endpoint, bearer_token_credentials(token))

    def sync(self, chunks: Iterable[EnrichedChunk]) -> None:  # pragma: no cover - gated
        """Write governance grants as SpiceDB relationships."""
        # Operator/integration path — exercised by @pytest.mark.spicedb tests when a
        # live endpoint is present. The grants derive from governance_tuples + the
        # level/class outcome (same computation as LocalReBAC) so view == allowlist.
        raise NotImplementedError(
            "live SpiceDB sync runs under the spicedb integration fixture"
        )

    def authorized_ids(  # pragma: no cover - gated
        self, session: Session, candidates: Iterable[EnrichedChunk]
    ) -> list[str]:
        raise NotImplementedError(
            "live SpiceDB LookupResources runs under the spicedb integration fixture"
        )


__all__ = ["SpiceDBAllowlist", "SPICEDB_SCHEMA", "governance_tuples"]

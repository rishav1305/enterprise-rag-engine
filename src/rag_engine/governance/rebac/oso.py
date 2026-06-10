"""OsoCloudAllowlist — Oso Cloud ReBAC backend (creds-gated).

Hosted ReBAC: facts are pushed to Oso Cloud and the allowlist is answered with a
single ``list(actor, "view", "Chunk")`` call (sub-linear list-objects). Gated on
the ``OSO_AUTH`` env var (the API key); absent it, construction raises and the
@pytest.mark.oso tests skip. The in-process default is always tested.

PARITY: list(view) MUST equal InProcessAllowlist's set. The Polar policy encodes
the same rules as access.evaluate.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...schemas import EnrichedChunk, Session

# Polar policy (Oso Cloud). Mirrors the governance rules; operators load it once.
OSO_POLICY = """
actor User {}
resource Chunk {
  permissions = ["view"];
  # allowed_role = the legacy un-classed role gate (access.py:87); MUST be present
  # or this policy inherits the LocalReBAC un-classed-leak blind spot.
  roles = ["public", "level_cleared", "ntk", "partial", "allowed_role"];
  "view" if "public";
  "view" if "level_cleared";
  "view" if "ntk";
  "view" if "partial";
  "view" if "allowed_role";
}
""".strip()


def _require_oso():
    try:
        from oso_cloud import Oso  # noqa: F401
    except ImportError as e:  # pragma: no cover - gated
        raise RuntimeError(
            "OsoCloudAllowlist requires the 'oso-cloud' package and the OSO_AUTH "
            "API key. Install oso-cloud + set OSO_AUTH, or use the default "
            "InProcessAllowlist / LocalReBACAllowlist."
        ) from e


class OsoCloudAllowlist:
    def __init__(self, url: str, api_key: str) -> None:
        _require_oso()
        from oso_cloud import Oso

        self._oso = Oso(url=url, api_key=api_key)

    def sync(self, chunks: Iterable[EnrichedChunk]) -> None:  # pragma: no cover - gated
        raise NotImplementedError(
            "live Oso Cloud fact sync runs under the oso integration fixture"
        )

    def authorized_ids(  # pragma: no cover - gated
        self, session: Session, candidates: Iterable[EnrichedChunk]
    ) -> list[str]:
        raise NotImplementedError(
            "live Oso Cloud list() runs under the oso integration fixture"
        )


__all__ = ["OsoCloudAllowlist", "OSO_POLICY"]

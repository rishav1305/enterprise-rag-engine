"""CI hygiene guard — the P0.2b headline tests must RUN, not skip (no false-green).

The drop-before-search (allowlist pre-filter) + recall tests use
``pytest.importorskip("turbovec")``, which silently SKIPS the whole module if
turbovec is missing — a green CI that proves nothing and could mask a security
regression. turbovec is now a PINNED dev dependency, so in the dev/CI env these
tests MUST be collected and executed. This guard fails (not skips) if turbovec is
absent, turning a silent skip into a loud CI failure.

Skipped only outside the dev env (RAG_DEV_ENV unset AND turbovec genuinely
absent) so a minimal runtime-only install isn't punished. CI sets RAG_DEV_ENV=1.
"""

from __future__ import annotations

import importlib.util
import os

import pytest


def _turbovec_installed() -> bool:
    return importlib.util.find_spec("turbovec") is not None


def test_turbovec_is_importable_in_dev_env():
    """Bare import — FAILS (does not skip) when turbovec should be present."""
    dev_env = os.getenv("RAG_DEV_ENV") == "1"
    if not dev_env and not _turbovec_installed():
        pytest.skip("runtime-only env (set RAG_DEV_ENV=1 in CI to enforce)")
    import turbovec  # noqa: F401  -- hard import; ModuleNotFoundError fails the test
    assert _turbovec_installed()


def test_headline_p0_2b_tests_are_collected_not_skipped(pytestconfig):
    """Assert the security/recall test modules are present AND, when turbovec is
    installed, are not skip-only. Guards against the importorskip false-green."""
    if not _turbovec_installed():
        dev_env = os.getenv("RAG_DEV_ENV") == "1"
        if dev_env:
            pytest.fail("turbovec missing in dev env — headline P0.2b tests would skip")
        pytest.skip("runtime-only env")
    # turbovec present -> the headline test modules import their subjects cleanly
    # (if importorskip were masking a real import error, this would raise here).
    from rag_engine.governance.allowlist import authorized_chunk_ids  # noqa: F401
    from rag_engine.retrieval.turbovec_index import TurboVecIndex  # noqa: F401
    # sanity: a tiny end-to-end exercise of the drop-before-search path runs
    # (dim must be a multiple of 8 for TurboQuant).
    import numpy as np
    v = np.eye(8, dtype="float32")[:4]  # 4 unit vectors in 8-dim
    idx = TurboVecIndex(dim=8)
    idx.add(["chunk:a", "chunk:b", "chunk:c", "chunk:d"], v)
    hits = idx.search(v[0], k=4, allowlist_chunk_ids=["chunk:b", "chunk:c"])
    assert {h.chunk_id for h in hits} <= {"chunk:b", "chunk:c"}  # pre-filter runs

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
import shutil
from pathlib import Path

import pytest


def _turbovec_installed() -> bool:
    return importlib.util.find_spec("turbovec") is not None


def _surreal_binary() -> str | None:
    """Locate the surreal binary (PATH or the documented ~/.surrealdb/surreal)."""
    found = shutil.which("surreal")
    if found:
        return found
    fallback = Path.home() / ".surrealdb" / "surreal"
    return str(fallback) if fallback.exists() else None


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


# ---- surreal binary no-skip guard (mirrors the turbovec guard) ----------
def test_surreal_binary_available_in_dev_env():
    """The 210-cell SurrealDB-parity + store tests need the `surreal` binary;
    without it they SKIP via the surreal_local fixture (false-green on the
    governance regression net). In a dev env (RAG_DEV_ENV=1) the binary MUST be
    present — fail loudly, don't skip."""
    dev_env = os.getenv("RAG_DEV_ENV") == "1"
    binary = _surreal_binary()
    if not dev_env and binary is None:
        pytest.skip("runtime-only env (set RAG_DEV_ENV=1 in CI to enforce)")
    assert binary is not None, (
        "surreal binary not found (PATH or ~/.surrealdb/surreal) — the SurrealDB "
        "parity/store tests would silently skip. Install surreal for the local CI gate."
    )
    assert importlib.util.find_spec("surrealdb") is not None, "surrealdb SDK missing"


def test_surreal_parity_tests_run_when_binary_present():
    """If the surreal binary is present, the 210-cell parity test module imports
    its subjects cleanly (guards against a masked import error skipping parity)."""
    if _surreal_binary() is None:
        if os.getenv("RAG_DEV_ENV") == "1":
            pytest.fail("surreal binary missing in dev env — 210-cell parity would skip")
        pytest.skip("runtime-only env")
    from rag_engine.catalog.surreal_connector import SurrealConnector  # noqa: F401
    from rag_engine.store.surreal import SurrealStore  # noqa: F401
    from seeds.targets.surreal_target import load_estate  # noqa: F401


def _sqlglot_installed() -> bool:
    return importlib.util.find_spec("sqlglot") is not None


def test_sqlglot_is_importable_in_dev_env():
    """sqlglot powers the P0.3a SQL-safety gate (read-only AST + cost guard). In a
    dev env it MUST be present — FAIL loudly (not skip), so the SQL-safety tests
    can't silently skip = false-green on the SECURE gate."""
    dev_env = os.getenv("RAG_DEV_ENV") == "1"
    if not dev_env and not _sqlglot_installed():
        pytest.skip("runtime-only env (set RAG_DEV_ENV=1 in CI to enforce)")
    import sqlglot  # noqa: F401  -- hard import; ModuleNotFoundError fails the test
    assert _sqlglot_installed()
    # the SQL-safety subjects import cleanly (guards against a masked import error)
    from rag_engine.connectors.bigquery import GuardedBigQuery  # noqa: F401
    from rag_engine.sql.ast_gate import assert_read_only  # noqa: F401

"""Pytest fixtures + path setup so `rag_engine` imports without an install."""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_engine import RAGPipeline, Session  # noqa: E402

CORPUS = ROOT / "corpus"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def surreal_local():
    """Ephemeral in-memory SurrealDB for the self-host (CI/dev) path.

    Skips cleanly when the `surreal` binary or the python SDK is unavailable, so
    a SurrealDB-less CI still runs the rest of the suite.
    """
    surreal_bin = shutil.which("surreal") or str(Path.home() / ".surrealdb" / "surreal")
    if not Path(surreal_bin).exists():
        pytest.skip("surreal binary not available")
    pytest.importorskip("surrealdb")
    port = _free_port()
    proc = subprocess.Popen(
        [surreal_bin, "start", "--user", "root", "--pass", "root",
         "--bind", f"127.0.0.1:{port}", "memory"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Readiness poll (RESILIENT): a port-open check alone races — the TCP socket
    # accepts before the RPC layer is ready, which surfaced as a ~1/6 transient
    # startup failure (test-coverage flake watch). So probe the actual SDK
    # signin/use round-trip (the real readiness signal), with a longer deadline for
    # cold hosts.
    from surrealdb import Surreal

    deadline = time.time() + 30
    ready = False
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                pass
            # port is open — now confirm the RPC layer actually answers.
            probe = Surreal(f"ws://127.0.0.1:{port}/rpc")
            probe.signin({"username": "root", "password": "root"})
            probe.use("meridian", "test")
            ready = True
            break
        except Exception as e:  # OSError (port) or SDK error (RPC not ready yet)
            last_err = e
            time.sleep(0.1)
    if not ready:
        proc.terminate()
        proc.wait(timeout=10)
        pytest.fail(f"surreal did not become RPC-ready on port {port} within 30s "
                    f"(last error: {last_err!r})")
    try:
        yield {"dsn": f"ws://127.0.0.1:{port}/rpc", "user": "root",
               "pass": "root", "ns": "meridian", "db": "test"}
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="session")
def pipeline() -> RAGPipeline:
    p = RAGPipeline()
    p.index_corpus(CORPUS)
    return p


@pytest.fixture
def intern() -> Session:
    return Session(user_id="intern-1", roles=["INTERN"], clearance_level=1)


@pytest.fixture
def cfo() -> Session:
    return Session(user_id="cfo-1", roles=["C_SUITE", "FINANCE"], clearance_level=5)


@pytest.fixture
def support() -> Session:
    return Session(user_id="cs-1", roles=["CUSTOMER_SUPPORT"], clearance_level=1)

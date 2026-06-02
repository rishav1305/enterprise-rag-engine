"""Pytest fixtures + path setup so `rag_engine` imports without an install."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_engine import RAGPipeline, Session  # noqa: E402

CORPUS = ROOT / "corpus"


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

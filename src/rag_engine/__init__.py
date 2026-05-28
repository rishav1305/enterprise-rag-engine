"""Adaptive Enterprise RAG engine with permission-aware governance."""

from .config import EngineConfig
from .pipeline import RAGPipeline
from .schemas import (
    Citation,
    Document,
    EnrichedChunk,
    GovernanceDecision,
    RAGArchitecture,
    RAGResponse,
    ScoredChunk,
    SecurityContext,
    Session,
)

__all__ = [
    "EngineConfig",
    "RAGPipeline",
    "Document",
    "EnrichedChunk",
    "SecurityContext",
    "Session",
    "ScoredChunk",
    "Citation",
    "GovernanceDecision",
    "RAGArchitecture",
    "RAGResponse",
]

__version__ = "0.1.0"

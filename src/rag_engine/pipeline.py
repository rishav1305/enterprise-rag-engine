"""The Adaptive Enterprise RAG pipeline — wires the five layers together.

Flow per query:
    route (L3) -> hybrid retrieve (L4) -> security filter (L5) ->
    build citations (L5) -> generate from admitted context only.

Indexing (run once) flows:
    load (L1) -> chunk (L1) -> contextual anchors (L2) -> index (L4).

Backends are chosen from :class:`EngineConfig` so you can flip the
contextualizer or generator to their Anthropic implementations with an env var
and no code change.
"""

from __future__ import annotations

from pathlib import Path

from .config import EngineConfig
from .enrichment.base import Contextualizer
from .enrichment.local import LocalHeuristicContextualizer
from .generation.base import Generator
from .generation.extractive import ExtractiveGenerator
from .governance.audit import AuditLog
from .governance.citations import build_citations
from .governance.filter import SecurityFilter
from .ingestion.markdown_loader import MarkdownLoader, chunk_document
from .retrieval.hybrid import HybridRetriever
from .routing.heuristic_router import HeuristicRouter
from .schemas import Document, EnrichedChunk, RAGResponse, Session


def _build_contextualizer(cfg: EngineConfig) -> Contextualizer:
    if cfg.contextualizer == "anthropic" and cfg.use_anthropic:
        from .enrichment.anthropic_contextualizer import AnthropicContextualizer

        return AnthropicContextualizer(cfg)
    return LocalHeuristicContextualizer()


def _build_generator(cfg: EngineConfig) -> Generator:
    if cfg.generator == "anthropic" and cfg.use_anthropic:
        from .generation.anthropic_generator import AnthropicGenerator

        return AnthropicGenerator(cfg)
    return ExtractiveGenerator()


class RAGPipeline:
    def __init__(
        self,
        config: EngineConfig | None = None,
        retriever: HybridRetriever | None = None,
        contextualizer: Contextualizer | None = None,
        generator: Generator | None = None,
    ) -> None:
        self.config = config or EngineConfig()
        self.router = HeuristicRouter()
        self.contextualizer = contextualizer or _build_contextualizer(self.config)
        self.retriever = retriever or HybridRetriever(self.config)
        self.security = SecurityFilter()
        self.generator = generator or _build_generator(self.config)
        self.audit = AuditLog()
        self._chunks: list[EnrichedChunk] = []

    # ---- indexing -----------------------------------------------------
    def index_documents(self, docs: list[Document]) -> int:
        all_chunks: list[EnrichedChunk] = []
        for doc in docs:
            chunks = chunk_document(doc, self.config)
            chunks = self.contextualizer.annotate(doc, chunks)
            all_chunks.extend(chunks)
        self._chunks = all_chunks
        self.retriever.index(all_chunks)
        return len(all_chunks)

    def index_corpus(self, corpus_dir: str | Path) -> int:
        return self.index_documents(MarkdownLoader(corpus_dir).load())

    # ---- query --------------------------------------------------------
    def query(self, question: str, session: Session) -> RAGResponse:
        architecture = self.router.route(question)
        candidates = self.retriever.retrieve(question)
        admitted, trail = self.security.apply(candidates, session)
        self.audit.record(session, question, trail)

        citations = build_citations(admitted, self.config)
        answer = self.generator.generate(question, admitted)
        blocked = sum(1 for d in trail if d.decision == "deny")

        return RAGResponse(
            query=question,
            answer=answer,
            architecture=architecture,
            citations=citations,
            access_denied=(len(admitted) == 0 and len(candidates) > 0),
            retrieved=len(candidates),
            admitted=len(admitted),
            blocked=blocked,
            governance_trail=trail,
        )

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
from typing import TYPE_CHECKING

from .config import EngineConfig

if TYPE_CHECKING:
    from .catalog.registry import CatalogRegistry
    from .retrieval.turbovec_retriever import TurboVecRetriever
from .enrichment.base import Contextualizer
from .enrichment.local import LocalHeuristicContextualizer
from .generation.base import Generator
from .generation.extractive import ExtractiveGenerator
from .governance.audit import AuditLog
from .governance.citations import build_citations
from .governance.filter import SecurityFilter
from .ingestion.markdown_loader import MarkdownLoader, chunk_document
from .observability.tracer import Tracer
from .retrieval.hybrid import HybridRetriever
from .routing.heuristic_router import HeuristicRouter
from .schemas import Document, EnrichedChunk, RAGResponse, ScoredChunk, Session


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
        catalog: "CatalogRegistry | None" = None,
        vector_retriever: "TurboVecRetriever | None" = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.config = config or EngineConfig()
        self.router = HeuristicRouter()
        # P0.11a W1: per-request tracing. Spans carry METRIC-ONLY attributes; a
        # LangfuseExporter (creds-gated) is filtered through LANGFUSE_ATTR_ALLOWLIST
        # so content can never reach Langfuse. Defaults to an in-memory tracer (no
        # creds, no network) so the hot path never depends on export.
        self.tracer = tracer or Tracer(otel=False)
        self.contextualizer = contextualizer or _build_contextualizer(self.config)
        self.retriever = retriever or HybridRetriever(self.config)
        self.security = SecurityFilter()
        self.generator = generator or _build_generator(self.config)
        self.audit = AuditLog()
        # Catalog of asset/column policy (P0.1b). Optional: when present, the
        # pipeline can resolve a chunk's governing CatalogAsset by parent_doc_id.
        self.catalog: "CatalogRegistry | None" = catalog
        # P0.2c: the LIVE session-aware vector path. When present, vector-mode
        # queries route through it (allowlist pre-filter at the index + mandatory
        # rerank). The L5 SecurityFilter still runs after (defense in depth).
        self.vector_retriever: "TurboVecRetriever | None" = vector_retriever
        self._chunks: list[EnrichedChunk] = []
        # P0.11a W2: permission-aware semantic cache. Optional; when cfg.cache_enabled
        # the pipeline checks the cache at query entry with the REAL govern_fn (re-run
        # SecurityFilter), so a cached answer is re-governed for the requester and a
        # partial re-redaction forces a fresh recompute (miss). Defaults to an
        # in-memory cache (no creds).
        self.cache = None
        if self.config.cache_enabled and self.config.cache_backend == "memory":
            from .cache.semantic_cache import SemanticCache
            from .retrieval.embedders import HashingEmbedder

            self.cache = SemanticCache(
                embedder=HashingEmbedder(dim=self.config.embedding_dim),
                similarity_threshold=self.config.cache_similarity_threshold,
                ttl_seconds=self.config.cache_ttl_seconds,
                max_entries=self.config.cache_max_entries,
            )
        # P0.11a W3: corrective self-RAG loop. Optional; when cfg.selfrag_enabled the
        # loop drives retrieve->grade->(re-retrieve)->generate->grade with a real
        # SESSION-SCOPED retrieve_fn (self._retrieve_for_session) — it reformulates
        # query text only and threads the fixed session, so every iteration is
        # permission-pre-filtered + the loop self-applies SecurityFilter. Fake grader
        # by default (no creds).
        self.selfrag_enabled = self.config.selfrag_enabled

    def asset_for(self, parent_doc_id: str):
        """Resolve the governing CatalogAsset for a chunk's source, if cataloged."""
        if self.catalog is None:
            return None
        try:
            return self.catalog.get(parent_doc_id)
        except KeyError:
            return None

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

    def index_multimodal(self, source_doc: Document, raw, extractor) -> int:
        """W6 — ingest a NON-TEXT source through guarded_extract.

        The extractor runs under guarded_extract (a crash or oversized payload is
        AUDITED, not silent), and every produced chunk INHERITS the source doc's
        SecurityContext (no declassify-by-extraction). The chunks are added to the
        index + governed by the SAME L5 SecurityFilter as text at query time — so a
        masked image is withheld, a denied table is dropped, identically. Returns the
        number of multimodal chunks added.
        """
        from .multimodal.robust import guarded_extract

        mm_chunks = guarded_extract(
            extractor, source_doc, raw,
            audit_sink=getattr(self, "audit_sink", None),
            max_payload_bytes=self.config.multimodal_max_payload_bytes,
        )
        if mm_chunks:
            self._chunks = list(self._chunks) + list(mm_chunks)
            self.retriever.index(self._chunks)
        return len(mm_chunks)

    def index_corpus(self, corpus_dir: str | Path) -> int:
        return self.index_documents(MarkdownLoader(corpus_dir).load())

    # ---- query --------------------------------------------------------
    def apply_change(self, event) -> bool:
        """W7 — apply a CDC ChunkChangeEvent to the live pipeline (store + cache).

        Governance propagation: a reclassify/delete updates the in-memory chunk set
        (so the next query re-derives governance from the NEW classification) AND
        invalidates the semantic cache for that chunk (so a stale permissive entry
        can't serve now-restricted content). Version-ordered + idempotent via the
        CdcProcessor. Returns True if applied, False if dropped (stale/replay).
        """
        from .cdc.events import ChangeOp

        # a PERSISTENT processor (built once) so its per-chunk version-ordering map
        # survives across events — a stale/replayed event is dropped correctly.
        proc = self._cdc_processor()
        applied = proc.apply(event)
        if applied and event.op is not ChangeOp.DELETE:
            self.retriever.index(self._chunks)
        return applied

    def _cdc_processor(self):
        """Lazily build + cache the pipeline's CdcProcessor (in-memory store+cache
        adapters). One instance so version-ordering state persists across events."""
        if getattr(self, "_cdc", None) is not None:
            return self._cdc
        from .cdc.processor import CdcProcessor

        pipe = self

        class _InMemStore:
            def upsert_chunk(self, chunk):
                from .schemas import EnrichedChunk, SecurityContext
                cid = chunk["chunk_id"]
                sec = SecurityContext(
                    allowed_roles=chunk.get("allowed_roles", []),
                    clearance_level=chunk.get("level", 0),
                    sensitivity_class=chunk.get("cls", ""),
                    need_to_know_roles=chunk.get("need_to_know", []),
                )
                new = EnrichedChunk(chunk_id=cid, parent_doc_id=chunk.get("asset_id", cid),
                                    parent_title=chunk.get("asset_id", cid),
                                    content=chunk.get("text", ""), security=sec)
                pipe._chunks = [c for c in pipe._chunks if c.chunk_id != cid] + [new]

            def delete_chunk(self, chunk_id):
                pipe._chunks = [c for c in pipe._chunks if c.chunk_id != chunk_id]

        class _NoCache:
            def invalidate_chunk(self, chunk_id):
                pass

        cache_adapter = self.cache if self.cache is not None else _NoCache()
        self._cdc = CdcProcessor(_InMemStore(), cache_adapter)
        return self._cdc

    def query_warehouse(self, question: str, session: Session, agent, asset):
        """W5 — answer a warehouse-SQL question through the text-to-SQL agent with the
        mask flag DERIVED from governance over the warehouse asset for this session
        (NOT a literal), and the ColumnPolicy sourced from the catalog asset.

        The agent already: validates the drafted SQL via the AST gate, runs it through
        GuardedBigQuery (cost guard), and masks result rows BY AST SOURCE before the
        model. Here we make the mask decision session-driven: if the session would get
        a non-`allow` decision on the asset, result rows are masked.
        """
        from .governance import access
        from .texttosql.agent import SqlAnswer

        # synthetic chunk carrying the asset's SecurityContext -> the real decision.
        probe = EnrichedChunk(chunk_id=asset.asset_id, parent_doc_id=asset.asset_id,
                              parent_title=asset.asset_id, content="",
                              security=asset.security)
        decision = access.evaluate(probe, session).decision

        # FIX1: a DENY decision short-circuits BEFORE drafting/running SQL — the text
        # path drops denied content before the model, the warehouse path must too.
        # mask-only column redaction would leak a non-flagged column raw to a denied
        # session; deny means NO rows reach the model at all (fail-closed).
        if decision == "deny":
            return SqlAnswer(question=question, sql="", rows=[],
                             answer="You are not authorized to access this data.",
                             masked=True, columns=tuple(asset.columns),
                             access_denied=True)

        mask = decision != "allow"   # allow -> raw; mask/partial -> column-masked
        # ColumnPolicy from the catalog asset (single governance source), not literals.
        agent.columns = tuple(asset.columns)
        return agent.answer(question, mask=mask)

    def _run_corrective_loop(self, question: str, session: Session, request_id: str) -> str:
        """Run the W3 corrective loop and return its answer (or an abstain message).

        The loop's retrieve_fn is the SAME session-scoped retrieve the pipeline uses,
        so a corrective re-retrieval is permission-pre-filtered; the loop also self-
        applies SecurityFilter (mask/partial -> redacted) before grading/generating.
        """
        from .selfrag.grader import FakeGrader
        from .selfrag.loop import CorrectiveLoop

        loop = CorrectiveLoop(
            retrieve_fn=self._retrieve_for_session,   # REAL session-scoped retriever
            generator=self.generator,
            grader=FakeGrader(
                relevance_threshold=self.config.selfrag_relevance_threshold,
                groundedness_threshold=self.config.selfrag_groundedness_threshold,
            ),
            max_iterations=self.config.selfrag_max_iterations,
            tracer=self.tracer, request_id=request_id,
        )
        result = loop.run(question, session)
        if result.abstained:
            return "I don't have enough authorized, grounded context to answer that."
        return result.answer

    def _retrieve_for_session(self, question: str, session: Session):
        """The session-scoped retrieval seam (the loop's retrieve_fn reuses THIS).

        Vector path: TurboVecRetriever already allowlist-pre-filters at the index
        (drops denied) + reranks. Lexical fallback: permission-blind retrieve (the L5
        SecurityFilter is the only gate — the original INTERN-vs-CFO demo story). In
        BOTH cases the L5 SecurityFilter runs downstream (defense in depth).
        """
        if self.vector_retriever is not None:
            return self.vector_retriever.retrieve_for_session(question, session)
        return self.retriever.retrieve(question)

    def _govern_fn(self, chunk_ids, session) -> list[str]:
        """REAL re-governance for a cache hit: re-run SecurityFilter over the stored
        chunk ids for this session, return the authorized (decision != deny) ids.

        This is the cache's permission re-derivation — NOT identity. Combined with the
        cache's miss-on-any-redaction, a stale cache entry can never serve content the
        requester is no longer cleared for.
        """
        by_id = {c.chunk_id: c for c in self._chunks}
        scored = [ScoredChunk(chunk=by_id[cid], score=1.0)
                  for cid in chunk_ids if cid in by_id]
        admitted, _trail = self.security.apply(scored, session)
        return [sc.chunk.chunk_id for sc in admitted]

    def query(self, question: str, session: Session) -> RAGResponse:
        request_id = self.tracer.new_request_id()
        architecture = self.router.route(question)

        # P0.11a W2: permission-aware cache check (real govern_fn). A hit is re-governed
        # for THIS session; a partial re-redaction -> miss (recompute). Never serves a
        # cross-clearance or now-restricted answer.
        if self.cache is not None:
            hit = self.cache.get(question, session, self._govern_fn)
            if hit is not None:
                from .cache.observability import record_cache_hit

                record_cache_hit(
                    request_id=request_id, similarity=hit.similarity,
                    scope_fp=hit.scope_fp, n_chunks=len(hit.chunk_ids),
                    tracer=self.tracer, audit_sink=None,
                )
                admitted_chunks = [c for c in self._chunks if c.chunk_id in set(hit.chunk_ids)]
                return RAGResponse(
                    query=question, answer=hit.answer, architecture=architecture,
                    citations=build_citations(
                        [ScoredChunk(chunk=c, score=1.0) for c in admitted_chunks],
                        self.config),
                    access_denied=False, retrieved=len(hit.chunk_ids),
                    admitted=len(hit.chunk_ids), blocked=0,
                    # report the TRUE withheld count from put-time (the trail is empty
                    # on a hit, but the count is preserved) so warm == cold.
                    n_withheld=int(hit.metadata.get("n_withheld", 0)),
                    governance_trail=[],
                )
        # P0.11a W1: metric-only spans (NO question/answer/chunk text) around the
        # path. A LangfuseExporter is allowlist-filtered, so even these can't leak.
        mode = "vector" if self.vector_retriever is not None else "lexical"
        # W7: the query path selects the configured embedder_version (a re-embed
        # migration bumps this + invalidates the old cache); recorded on the span.
        with self.tracer.span("retrieve", request_id, mode=mode):
            candidates = self._retrieve_for_session(question, session)

        with self.tracer.span("govern", request_id, n_retrieved=len(candidates)):
            admitted, trail = self.security.apply(candidates, session)
        self.audit.record(session, question, trail)

        citations = build_citations(admitted, self.config)
        with self.tracer.span("generate", request_id, n_admitted=len(admitted)):
            if self.selfrag_enabled:
                # P0.11a W3: corrective loop with a real session-scoped retrieve_fn.
                # The loop reformulates query text only, threads the FIXED session, and
                # self-applies SecurityFilter — so every iteration is permission-pre-
                # filtered AND mask/partial-redacted. It generates over the loop's
                # governed context (never the raw candidates).
                answer = self._run_corrective_loop(question, session, request_id)
            else:
                answer = self.generator.generate(question, admitted)
        blocked = sum(1 for d in trail if d.decision == "deny")

        # P0.11a W2: cache the GOVERNED result keyed by the session's auth scope. The
        # stored chunk_ids are the ADMITTED (non-deny) ids; on a future hit the cache
        # re-governs them for the requester (real _govern_fn) before serving.
        n_withheld = sum(1 for d in trail if d.decision != "allow")
        if self.cache is not None:
            self.cache.put(question, session,
                           chunk_ids=[sc.chunk.chunk_id for sc in admitted],
                           answer=answer, n_withheld=n_withheld)

        return RAGResponse(
            query=question,
            answer=answer,
            architecture=architecture,
            citations=citations,
            access_denied=(len(admitted) == 0 and len(candidates) > 0),
            retrieved=len(candidates),
            admitted=len(admitted),
            blocked=blocked,
            n_withheld=n_withheld,
            governance_trail=trail,
        )

# 5 — Retrieval (vector + the 3 pre-filtered modes)

L4 retrieval is **session-scoped and pre-filtered**: every mode hands the index the session's
allowlist so unauthorized content is never a candidate (drop-before-search), and the L5
`SecurityFilter` still runs downstream (defense in depth).

## The vector path (P0.2c)

`retrieval/turbovec_retriever.py::TurboVecRetriever.retrieve_for_session(query, session)`:

1. derive the per-session **allowlist** (`governance.allowlist.authorized_chunk_ids`,
   decision ≠ deny);
2. embed the query and run `TurboVecIndex.search(…, allowlist_chunk_ids=allow)` — the permission
   pre-filter at the index;
3. **hydrate** the returned ids to full chunks (text + ACLs) from the `ChunkSource` (SurrealDB
   in production via `store/chunk_source.py::SurrealChunkSource`; in-memory in tests);
4. **always rerank** the coarse set (load-bearing, non-disableable);
5. return `ScoredChunk`s — the L5 `SecurityFilter` then masks `mask`/`partial` (the second gate).

The hybrid lexical fallback (`retrieval/hybrid.py`: BM25 ∥ dense → RRF → cross-encoder rerank) is
the original permission-**blind** path — the L5 filter is its only gate (the INTERN-vs-CFO demo
story).

## The three pre-filtered modes (P0.6)

Permission pre-filtering was extended beyond the vector mode to **graph / structured / lexical**,
each scoped `id IN $allow` **at the query** (drop-before-search), so a denied node/row/hit is
never a candidate:

| Mode | Retriever | Store method |
|---|---|---|
| graph (multi-hop) | `retrieval/graph_mode.py::GraphRetriever` | `SurrealStore.graph_neighbors(node, allow)` over `links` |
| structured (SQL-ish) | `retrieval/structured_mode.py::StructuredRetriever` | `SurrealStore.structured_rows(asset, allow)` |
| lexical (BM25) | `retrieval/lexical_mode.py::LexicalRetriever` | `SurrealStore.fulltext_search(query, allow)` |

Each retriever derives the allowlist via the swappable `AllowlistBackend` (`retrieval/mode_base.py`)
and is mutation-proven: bypass a mode's pre-filter → a denied chunk surfaces → the hardened test
fails (`tests/test_graph_prefilter.py`, `test_structured_prefilter.py`, `test_lexical_prefilter.py`).
The empty-allowlist case is fail-closed.

`retrieval/mode_router.py::ModeRouter` wires all three with one `AllowlistBackend` instance
(in-process default; ReBAC selectable), and is dispatched by the router's `RAGArchitecture`.

## The router (L3)

`routing/heuristic_router.py::HeuristicRouter.route(query) -> RAGArchitecture`
(`ADVANCED_HYBRID` / `GRAPH_RAG` / `AGENTIC_LOOP`) — a regex/keyword classifier, no LLM in the
hot path. A semantic router (`routing/semantic_router.py`) uses a local deterministic
`HashingEmbedder` `DenseEncoder` (also no LLM). The router selects the retrieval **mode** and is
the seam for partition pruning (tenant / time / geography / vertical).

**Wired-live vs gated:** the vector + 3 mode retrievers are wired into `RAGPipeline` (P0.11a W3/W4);
the mode retrievers are SurrealDB-backed (tested live via `surreal_local`). Voyage/Cohere live
embeddings + reranker are gated; the offline path is deterministic.

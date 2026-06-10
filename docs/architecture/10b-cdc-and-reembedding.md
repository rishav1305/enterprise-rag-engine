# 10b — CDC / streaming re-embedding (governance propagation)

This phase mutates data **under a live governance model**, so the risk is **propagation**: a data
change must never leave **stale authorization reachable**. Three sub-invariants (`cdc/`,
`store/surreal.py`, `cache/`), each fail-closed + mutation-proven.

## 1. DELETE / tombstone

`store/surreal.py::delete_chunk` removes the chunk (+ its `links` edges — SurrealDB cascades
RELATION edges with the node, with an explicit sweep backstop). The chunk becomes un-retrievable
in **all 3 modes** + dropped from the allowlist source; `cache.invalidate_chunk` evicts every
cache entry that referenced it. *Mutation:* skip delete or cache-invalidate → still
reachable / stale hit → `tests/test_cdc_delete.py` fails.

## 2. RECLASSIFICATION (the sharp one)

A chunk's `sensitivity_class`/ACL changes (B→F): the allowlist **re-derives from the live store
row** (the new cls/level), so an under-cleared session that could see it before is now **denied**;
AND the cache entries computed under the old class are **invalidated**, so a re-query is a MISS,
not a stale permissive hit. *Mutation:* skip cache-invalidate-on-reclassify → the stale permissive
entry is served → `tests/test_cdc_reclassify.py` fails (the leak-oracle equivalent).

## 3. RE-EMBEDDING preserves SecurityContext

`cdc/reembed.py::ReEmbedder` re-embeds chunks under a new `embedder_version`, changing **only** the
vector + version — `cls`/`level` (the governance-bearing stored columns) are byte-identical, so the
governance decision is unchanged. (Roles are `cls`-derived at allowlist time, not persisted — so
preserving `cls`+`level` preserves the full decision; `_PRESERVED` lists only the real stored
fields.) Resumable + batched; `cache.invalidate_version(old)` on completion. *Mutation:* drop `cls`
from `_PRESERVED` → governance changes → `tests/test_reembed.py` fails.

## The CDC engine

- `cdc/events.py::ChunkChangeEvent` — op (`insert`/`update`/`delete`/`reclassify`) + a **monotonic
  `source_version`**.
- `cdc/processor.py::CdcProcessor` — applies each event to **store + cache**; **version-ordered**
  (a stale/replayed event whose version ≤ last-applied is dropped → idempotent + ordering-safe
  under at-least-once/out-of-order delivery); **RESILIENT** (bounded retry → audited `cdc_dropped`,
  never silent); **TRANSPARENT** (span + audit per event).
- `pipeline.py::apply_change(event)` drives a persistent processor over the live pipeline (P0.11a W7)
  — a reclassify-up via the pipeline → the under-cleared session's next `query()` is denied + the
  cache invalidated, end-to-end (`tests/test_pipeline_cdc.py`).

**Wired-live vs gated:** the processor is hardened against an injected event sequence (in-memory /
fixture). The live change-stream connector is a tracked follow-on with a **hard requirement**:
`source_version` MUST be unique-and-strictly-increasing **per event** (a source LSN / commit
timestamp / sequence), not per logical state — the `≤`-drop ordering guard would otherwise silently
drop a second same-version change.

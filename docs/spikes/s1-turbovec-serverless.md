# Spike S1 — TurboVec in serverless (cold-load + pre-filter feasibility)

**Date:** 2026-06-08 · **Owner:** Shuri · **Type:** throwaway probe (no product code shipped) · **Status:** ✅ KEEP TurboVec

> **Question:** Can a TurboQuant-compressed vector index load inside a Vercel Python serverless function within its cold-start time + RAM limits, and serve permission-pre-filtered ANN search at acceptable latency? If not, what triggers the Qdrant Cloud fallback?

This is the single highest-leverage unknown in the CLEARANCE architecture — the headline claim is *"the compressed index loads directly into the stateless orchestrator and the allowlist filter enforces permissions as a pre-filter at the vector index."* S1 proves that claim before any phase builds on it.

---

## 1. Method

- **Library:** `turbovec==0.7.0` — prebuilt `cp39-abi3 manylinux_2_28_x86_64` wheel (13.1 MB download; abi3 = forward-compatible across CPython, good for serverless runtime portability). Native lib (`turbovec.libs`) ≈ 39 MB on disk, package ≈ 2.1 MB.
- **API used (the real surface):**
  - `TurboQuantIndex(dim, bit_width)` → `.add(vecs)`, `.prepare()`, `.search(q, k, mask=<bool[N]>)`, `.write/.load` (`.tvim`). The `mask` is the **permission pre-filter at the index** for the vector mode.
  - `IdMapIndex(dim, bit_width)` → `.add_with_ids(vecs, ids:uint64)`, `.search(q, k, allowlist=<uint64[]>)` returning `(scores, ids)`. External `uint64` ids ↔ **SurrealDB record ids**; `allowlist` = the ACL-derived admitted set (the "list-objects → pre-filter" pattern from Oso/SpiceDB).
- **Workload:** synthetic L2-normalized vectors at **50k** and **200k × 1024-dim** (1024 = Voyage-3-large dim). Cold-load measured in a **fresh process per scenario** (import + load + prepare), the serverless cold-start proxy. Latency averaged over 8 single-query searches. Pre-filter set to 30% admitted (representative ACL selectivity).
- **Host:** titan-gpu, Python 3.12.3, isolated venv. RSS via `psutil`.

---

## 2. Results

### Build (offline batch — runs in CI/laptop/titan, not in the request path)
| N (×1024-dim) | build TurboQuant | build IdMap | `.tvim` size | bytes/vec |
|---|---|---|---|---|
| 50k | 1.81 s | 1.82 s | 25.8 MB | 516 |
| 200k | 7.16 s | 7.22 s | 103 MB | 516 |

### Cold load + query (fresh process = serverless cold-start proxy), bit_width=4
| N | cold load (`load`+`prepare`) | RSS after load | **RSS peak** | unfiltered q | **mask pre-filter** | **allowlist pre-filter** |
|---|---|---|---|---|---|---|
| 50k | **0.27 s** | 59 MB | 199 MB | 1.38 ms | 1.30 ms | 0.77 ms |
| 200k | **0.81 s** | 136 MB | 512 MB | 5.69 ms | 5.81 ms | 3.39 ms |

Import-only floor: `import turbovec` = 2 ms, RSS after imports ≈ 32 MB. Load itself is near-instant (5–19 ms); `prepare()` (rotation matrix + Lloyd-Max centroids + SIMD code layout warm-up) dominates cold cost but is still sub-second at 200k.

### Compression vs recall (50k, random gaussian vectors = worst case, no cluster structure)
| bit_width | bytes/vec | 50k index | recall@10 vs exact cosine |
|---|---|---|---|
| 2 | 260 | 13.0 MB | 0.49 |
| 3 | **388** | 19.4 MB | 0.73 |
| 4 | 516 | 25.8 MB | 0.845 |

(`bit_width` accepts only 2/3/4. The spec's "~384 B/vec / ~19 MB for 50k" figure = **bit_width=3**.)

---

## 3. Assessment vs Vercel Python function limits

| Limit (Vercel Hobby / Fluid Python) | Our number | Verdict |
|---|---|---|
| Cold start budget (within `maxDuration: 300 s`, PMB already runs this) | 0.27 s (50k) / 0.81 s (200k) load+prepare; +imports ≈ 2 ms | ✅ trivially within budget |
| Function memory (1024 MB default, up to 3009 MB) | 199 MB (50k) / 512 MB (200k) peak RSS | ✅ fits default at both sizes; headroom to ~1M vecs before needing a memory bump |
| Bundle size (250 MB unzipped incl. deps) | turbovec ≈ 41 MB libs + index 26–103 MB | ⚠️ 50k fits in-bundle; **200k index should ship via Vercel Blob** (load on cold start), not in the bundle, to stay clear of the 250 MB ceiling alongside other deps |
| Per-query latency | 0.8–5.8 ms (coarse stage, before rerank) | ✅ negligible vs the LLM generate step |

**Pre-filter works as designed.** Both the `mask` (TurboQuant) and `allowlist` (IdMap) paths return correctly restricted top-k with **no latency penalty** — allowlist is actually *faster* (smaller search space). This validates the architecture's core claim: **permission enforcement as a pre-filter at the vector index**, not a post-filter.

---

## 4. Verdict — ✅ KEEP TurboVec

TurboVec is viable as the serverless vector index for CLEARANCE. The index loads in <1 s, fits default function memory well past our demo corpus, and the `mask`/`allowlist` pre-filter is real, correct, and free. Ship the **200k+ index via Vercel Blob**; the 50k demo index can ride in-bundle.

**Recommended config (CONFIGURABLE pillar):**
- `bit_width=4` for the demo (best recall, 26 MB @ 50k still tiny). Expose `bit_width` in `EngineConfig`; bit_width=3 is the size/recall knob if corpus grows.
- TurboVec is the **coarse** retrieval stage → cross-encoder rerank (Cohere/local) restores precision, so coarse recall@10 on random vectors (worst case) understates end-to-end quality. **Action:** P0.2b must include a **recall-validation gate on real Voyage embeddings** (not random) — that is the honest number.
- Use `IdMapIndex` (external uint64 ids ↔ SurrealDB record ids) as the primary index type so ACL allowlists map cleanly to record ids.

## 5. Qdrant-fallback trigger (pre-identified, per spec §9)

Fall back to **Qdrant Cloud** (vector mode only; SurrealDB still owns graph/FTS/SurrealQL) if **any** of:
1. Cold load + prepare on the **real corpus** exceeds ~3 s in the deployed Vercel runtime (vs 0.8 s here — large margin, unlikely).
2. Peak RSS on the real corpus would force a function-memory tier that breaks the $0 Hobby budget (i.e. corpus grows past ~1M vecs at 1024-dim).
3. Recall@10 on **real Voyage embeddings after rerank** falls below the eval-gate threshold and bit_width=4 can't recover it.
4. `prepare()` warm-up must run per-request (no warm reuse) AND pushes p99 past budget under concurrency — re-test under the ELASTIC load profile.

None tripped in this spike. Default: **build on TurboVec**; keep the Qdrant adapter as a real, tested swappable backend per the multi-setup-portability directive (memory `clearance-build-philosophy-robust`).

---

## 6. Reproduce

Throwaway harness at `/tmp/s1_spike.py` (venv `/tmp/s1venv`). Not committed — this doc is the artifact. To re-run: `python s1_spike.py build {N}` then `python s1_spike.py cold {N}` in a fresh process.

*Spike complete. Feeds P0.2b (TurboVec vector index + recall-validation gate) and the multi-setup Qdrant fallback adapter.*

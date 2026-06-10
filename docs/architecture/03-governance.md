# 3 — Governance (access.evaluate → the leak oracle)

Governance is the architecture, not a feature. It is **two stages, defense in depth**, plus the
adversarial oracle that gates CI.

## `access.evaluate` — the four-decision core

`governance/access.py::evaluate(chunk, session) -> GovernanceDecision`. The decision is one of
`allow` / `mask` / `partial` / `deny`, computed in this order (cite the module for the exact
branches):

1. **public** → `allow` (`sec.is_public`).
2. **PII masking leg** (class D, `_PII_CLASS`): L4+ → `allow` (cleared); L2–L3 → `mask`
   (`pii_masked`); below L2 → `deny`. (Customer PII is returned *masked*, never raw, below L4.)
3. **level gate**: session level < required → `deny` (`insufficient_clearance`).
4. **need-to-know gate** (non-monotonic): if the class has need-to-know roles and the session
   holds none → `deny` — UNLESS the chunk's `metadata.partial_for` grants a row-scoped
   **`partial`** (e.g. Engineer sees own-component security tickets). A dual-role holder with
   the full role skips this and falls through to `allow` (full access wins over partial).
5. **legacy allowed_roles gate** (un-classed chunks only): a non-public chunk with no class is
   denied if the session's roles are disjoint from `allowed_roles` — fail-closed. (Classed
   chunks are fully decided by the level + need-to-know gates above; re-gating them on roles was
   the historical `_CLASS_ROLES` drift bug, now fixed.)

`GovernanceDecision` records `chunk_id`, `parent_doc_id`, `decision`, `reason`,
`required_roles`, `session_roles`, `mask_reason`, `scope` — the per-chunk **audit trail**
(TRANSPARENT). This trail is operator-only at the API boundary (deep dive
[§11](11-demo-and-deploy-security.md): the client sees a `n_withheld` count, never the ACLs).

## Stage 1 — the allowlist PRE-filter (drop-before-search)

`governance/allowlist.py`. The set of chunk ids a session may retrieve (decision ≠ `deny`) is
handed to the index, so an unauthorized item is **never even a candidate**. The consistency
invariant: an id is on the allowlist **iff** the decision is not `deny` — `mask`/`partial` stay
on (retrievable, redacted downstream), so the pre-filter and post-filter agree exactly.

The allowlist **engine is swappable** behind `AllowlistBackend` (Protocol):
- `InProcessAllowlist` — the default + canonical decision source (scans candidates calling
  `access.evaluate`).
- `governance/rebac/`: `LocalReBACAllowlist` (zero-dep relationship-tuple kernel — the SpiceDB
  *model*, always-on so parity is provable no-creds), `SpiceDBAllowlist` (authzed
  LookupResources, gated), `OsoCloudAllowlist` (gated).

**Parity guard** (`tests/test_rebac_parity.py`): every backend must return **exactly**
`InProcessAllowlist`'s set across a session × class matrix spanning every governance leg. The
optimization changes the lookup cost (sub-linear list-objects), **never** the decision — a
superset is a leak, a subset over-denies.

## Stage 2 — the L5 SecurityFilter (redact)

`governance/filter.py::SecurityFilter.apply(candidates, session) -> (admitted, trail)`. At the
retrieval chokepoint, each chunk's decision is re-evaluated:
- `allow` → passes through;
- `deny` → **dropped** (never reaches the model — the model physically cannot leak it);
- `mask` / `partial` → **admitted but redacted** via `governance/masking.py::redact_chunk`:
  content → `[REDACTED]` (PII) / `[RESTRICTED]` (field-ACL) / `[PARTIAL …]` token. For non-text
  (image/table/ocr/figure) the raw payload is **withheld** (deep dive [§10c](10c-multimodal.md)).

Every decision is recorded to the trail regardless of admission (every drop/redaction is
explainable).

## Why both stages (and why every consumer self-governs)

Stage 1 makes denied content un-retrievable; stage 2 redacts mask/partial. **Any component that
consumes retrieved chunks outside the main pipeline must apply BOTH** — the semantic cache
re-governs on hit (deep dive [§9](09-semantic-cache.md)), the corrective loop self-applies
`SecurityFilter` every iteration (deep dive [§10](10-self-rag-loop.md)). This is the lesson the
P0.11a integration gate enforced: a standalone-safe component can leak once composed if it skips
a stage.

## The leak oracle (the CI gate)

- `tests/test_oracle_parity.py` — the engine's `access.evaluate` reproduces the **210-cell**
  golden set (`build_oracle`) with **zero mismatch**, across catalog backends (seed + SurrealDB).
- `tests/test_leak_oracle.py`, `tests/test_data_leakage.py` — adversarial scenarios (the
  INTERN-vs-CFO demo, the masked-not-raw PII pin, etc.).
- `tests/test_c1_over_vector_e2e.py` — C1 masking enforced over the live vector path.
- `tests/test_e2e_fully_wired_leak_oracle.py` (P0.11a) — the **master oracle**: all 210 cells
  through the **fully-wired** `RAGPipeline.query` (cache + corrective loop + tracer live),
  both selfrag modes. Mutation-proven: disable any component's governance step → the oracle
  leaks → `make ci` fails.

These run on every commit (`scripts/ci.sh`, 0-skip). The engine **cannot ship with a known
leak** — that is the headline credibility artifact.

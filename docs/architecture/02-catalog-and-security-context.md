# 2 — Catalog + SecurityContext

## SecurityContext — the unit of governance

`schemas.py::SecurityContext` (frozen Pydantic) is the ACL a chunk/asset carries:

| Field | Meaning |
|---|---|
| `allowed_roles: list[str]` | roles permitted to read (e.g. `["C_SUITE", "HR_ADMIN"]`) |
| `clearance_level: int` (0–5) | minimum clearance (0 = public, 5 = board-only) |
| `sensitivity_class: str` | the A–N class (the governance key) |
| `need_to_know_roles: list[str]` | roles satisfying need-to-know; empty ⇒ level + allowed_roles only |
| `owner_department: str` | originating department (provenance) |

Roles are upper-cased + de-duplicated by a validator (silent dupes would hide policy bugs).
`is_public` is a derived property: `clearance_level == 0 AND (no allowed_roles OR "PUBLIC")`.
**A chunk inherits the SecurityContext of its source** — including extracted/OCR'd content
(deep dive [§10c](10c-multimodal.md): no declassification-by-extraction).

## EnrichedChunk — the retrievable unit

`schemas.py::EnrichedChunk` = `chunk_id` + `parent_doc_id`/`parent_title` + `content` +
`contextual_anchor` (the L2 enrichment) + `security: SecurityContext` + `modality`
(`text`|`image`|`table`|`ocr`|`figure`, P0.10) + `metadata`. The `embedding_text` property
prepends the anchor to the content (Contextual Retrieval).

## CatalogAsset — the source-level governance record

`catalog/asset.py::CatalogAsset` describes an estate asset: `asset_id`, `vertical`,
`retrieval_mode`, `security: SecurityContext`, `sensitivity_class`, and a tuple of
`ColumnPolicy` (per-column masking — `name` / `pii` / `masked` / `mask_reason`). It also carries
the scale/provenance the funnel reads: `scale_badge` (e.g. "≈1.6B rows · ~400 GB"),
`provenance_url`, `row_count`.

`catalog/registry.py::CatalogRegistry` holds the discovered assets (`load(connector)` /
`get` / `all` / `by_vertical` / `by_class`). The pipeline resolves a chunk's governing asset by
`parent_doc_id` (`RAGPipeline.asset_for`). The text-to-SQL path sources its `ColumnPolicy`
**from the catalog asset** (single governance source), not from a literal kwarg — deep dive
[§6](06-sql-safety-and-text-to-sql.md).

## How a class becomes a SecurityContext

The single source is `seeds/access_matrix.py::CLASSES` (`min_level` + `need_to_know_roles` per
class). Connectors derive a chunk's `SecurityContext` from its class via
`governance.connector._CLASS_ROLES` (derived from `CLASSES` — no drift). This is why the
210-cell oracle is meaningful: the engine's per-chunk decision flows from the **same** class
definitions the golden set does.

**Wired-live vs gated:** the in-memory + SurrealDB-backed catalog are both tested; the demo API
wires a small synthetic `CatalogRegistry` for the funnel viz (deep dive
[§11](11-demo-and-deploy-security.md)). Live multi-connector estate ingestion is a tracked
follow-on.

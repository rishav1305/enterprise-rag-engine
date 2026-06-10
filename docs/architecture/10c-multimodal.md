# 10c — Multimodal (governed identically to text)

A non-text chunk (image / table / OCR'd-doc / figure) carries a full `SecurityContext` and is
governed by the **same pipeline** as text (`multimodal/`). Three sub-invariants, fail-closed +
mutation-proven.

## 1. Same pre-filter

A denied image/table/figure chunk is never a candidate in any mode (the allowlist is
modality-agnostic — it keys on chunk_id + ACLs). Cross-modal too: a text query that matches a
non-text caption is still allowlist-pre-filtered (`tests/test_multimodal_retrieval.py`).

## 2. Masking for non-text = WITHHOLD

You can't `[REDACTED]` a pixel inline, so a `mask`/`partial` non-text chunk has its **raw payload
withheld**. `governance/masking.py::redact_chunk` for a non-text chunk **deep-copies the metadata
down to a scalar allowlist** (`multimodal/payload.py::scrub_metadata_for_withhold` — keeps only
`modality`/`source_uri`/`page`/`ordinal`/`caption`; drops bytes/dicts/lists wherever they hide) +
a modality-aware withhold token. The allowlist is **fail-closed** — a new sidecar key a future live
extractor adds (a thumbnail/crop) is withheld by default. *Mutation:* a shallow strip (pop one key)
→ second-location / nested bytes survive → `tests/test_redact_multimodal.py` fails.

## 3. Extraction inherits classification (no declassify-by-extraction)

`multimodal/extract.py`: `ModalityExtractor` Protocol + `FakeImage/Table/Ocr/Figure` extractors.
Every produced chunk's `SecurityContext` **IS the source Document's** — text OCR'd from a class-F
scanned PDF is class-F, not public. *Mutation:* an extractor that mints a fresh public context →
an under-cleared session retrieves restricted extraction → `tests/test_multimodal_extract.py` fails.

## Cross-modal embedding + robustness

- `multimodal/embed.py::FakeMultimodalEmbedder` embeds each chunk's **text surface** (caption /
  OCR / table rendering) into the same space as a text query → cross-modal retrieval; the index
  holds **no raw bytes** (a payload can't be in the index).
- `multimodal/robust.py::guarded_extract` wraps any extractor: a crash → **audited** not silent
  (RESILIENT); a payload over `multimodal_max_payload_bytes` → **rejected + audited** (ELASTIC).
  `pipeline.py::index_multimodal` runs ingest through it (P0.11a W6).

**Wired-live vs gated:** the extractors + cross-modal embedder + ingest are local-tested with fake
providers; live multimodal embedding (Voyage-multimodal / CLIP) + live OCR (Tesseract/cloud) are
gated behind the same ABCs. The governance invariant holds for **any** embedder.

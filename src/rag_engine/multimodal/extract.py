"""Modality extractors (P0.10 T2) — produce chunks that INHERIT source governance.

The governance-critical contract: every chunk an extractor emits carries the SOURCE
``Document``'s ``SecurityContext`` verbatim. There is NO declassification-by-
extraction — text OCR'd from a class-F scanned PDF is class-F, an image cropped from
a restricted report is restricted. An extractor must NEVER mint a fresh/default
(public) SecurityContext; it copies the source's.

``Fake*Extractor`` are deterministic, no-creds implementations for tests + the
offline default. Live OCR (Tesseract/cloud) and live figure/table parsers are
creds/binary-gated behind the same ``ModalityExtractor`` Protocol.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..schemas import Document, EnrichedChunk
from .payload import attach_payload


@runtime_checkable
class ModalityExtractor(Protocol):
    def extract(self, source_doc: Document, raw: Any) -> list[EnrichedChunk]: ...


def _inherit_chunk(
    source_doc: Document, chunk_id: str, modality: str, content: str, payload: Any
) -> EnrichedChunk:
    """Build a chunk that INHERITS the source doc's SecurityContext (the whole point).

    ``security=source_doc.security`` — never a fresh/default context. The raw payload
    rides in metadata under the conventional key so governance can withhold it.
    """
    metadata: dict[str, Any] = {}
    if payload is not None:
        attach_payload(metadata, payload)
    return EnrichedChunk(
        chunk_id=chunk_id,
        parent_doc_id=source_doc.doc_id,
        parent_title=source_doc.title,
        content=content,
        modality=modality,
        security=source_doc.security,   # INHERITED — no declassify-by-extraction
        metadata=metadata,
    )


class FakeImageExtractor:
    """Deterministic image extractor: one image chunk with a caption + raw bytes."""

    def extract(self, source_doc: Document, raw: Any) -> list[EnrichedChunk]:
        return [_inherit_chunk(
            source_doc, f"{source_doc.doc_id}:img:0", "image",
            content=f"image from {source_doc.title}", payload=raw,
        )]


class FakeTableExtractor:
    """Deterministic table extractor: one table chunk with a text rendering + rows."""

    def extract(self, source_doc: Document, raw: Any) -> list[EnrichedChunk]:
        n_rows = len(raw) if isinstance(raw, list) else 0
        return [_inherit_chunk(
            source_doc, f"{source_doc.doc_id}:tbl:0", "table",
            content=f"table from {source_doc.title} ({n_rows} rows)", payload=raw,
        )]


class FakeOcrExtractor:
    """Deterministic OCR extractor: text 'recognised' from a scanned source.

    The recognised text inherits the SOURCE classification — the whole risk this
    guards against is treating OCR output as fresh/public text.
    """

    def extract(self, source_doc: Document, raw: Any) -> list[EnrichedChunk]:
        # deterministic "recognised text" stand-in (a real OCR engine fills this in).
        recognised = f"OCR text recognised from {source_doc.title}"
        return [_inherit_chunk(
            source_doc, f"{source_doc.doc_id}:ocr:0", "ocr",
            content=recognised, payload=raw,
        )]


class FakeFigureExtractor:
    """Deterministic figure extractor (chart/diagram with a caption + raw payload).

    A ``figure`` is a first-class modality (e.g. a chart cropped from a report). Like
    the others it INHERITS the source classification — a figure from a restricted
    report is restricted; its raw payload is withheld on a mask.
    """

    def extract(self, source_doc: Document, raw: Any) -> list[EnrichedChunk]:
        return [_inherit_chunk(
            source_doc, f"{source_doc.doc_id}:fig:0", "figure",
            content=f"figure from {source_doc.title}", payload=raw,
        )]


__all__ = [
    "ModalityExtractor", "FakeImageExtractor", "FakeTableExtractor",
    "FakeOcrExtractor", "FakeFigureExtractor",
]

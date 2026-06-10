"""Multimodal RAG (P0.10) — image / table / OCR chunks governed IDENTICALLY to text.

The headline invariant: a non-text chunk carries a full SecurityContext and is
pre-filtered + masked/withheld by the SAME governance as text. You can't [REDACTED]
a pixel inline, so a masked non-text chunk is WITHHELD (payload stripped). OCR/
extracted text inherits the source document's classification (no declassify-by-
extraction).
"""

from .payload import (
    MULTIMODAL_PAYLOAD_KEY,
    attach_payload,
    get_payload,
    strip_payload,
)
from .extract import (
    FakeFigureExtractor,
    FakeImageExtractor,
    FakeOcrExtractor,
    FakeTableExtractor,
    ModalityExtractor,
)
from .embed import FakeMultimodalEmbedder
from .robust import PayloadTooLarge, check_payload_size, guarded_extract

__all__ = [
    "MULTIMODAL_PAYLOAD_KEY", "attach_payload", "get_payload", "strip_payload",
    "ModalityExtractor", "FakeImageExtractor", "FakeTableExtractor", "FakeOcrExtractor",
    "FakeFigureExtractor", "FakeMultimodalEmbedder",
    "PayloadTooLarge", "check_payload_size", "guarded_extract",
]

"""Layer 1 — Ingestion seam.

Loaders turn a raw source into :class:`Document` objects whose
:class:`SecurityContext` is populated *from the source itself*. Swap this ABC
to ingest from SharePoint, Confluence, S3, a DMS, etc. — the rest of the
pipeline never changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import Document


class DocumentLoader(ABC):
    """Abstract base class for all ingestion sources."""

    @abstractmethod
    def load(self) -> list[Document]:
        """Return documents with security metadata already attached."""
        raise NotImplementedError

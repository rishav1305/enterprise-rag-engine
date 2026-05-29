"""Markdown/text loader + a deterministic, dependency-free chunker.

Each corpus file carries a YAML frontmatter block describing who may read it::

    ---
    title: Q3 Financial Projections
    doc_id: fin-q3-2026
    allowed_roles: [C_SUITE, FINANCE]
    clearance_level: 4
    owner_department: Finance
    summary: Confidential Q3 revenue and margin projections.
    ---
    <body...>

The loader refuses to emit a document without a SecurityContext, so an
un-tagged file fails loudly instead of silently defaulting to "public".
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..config import EngineConfig
from ..schemas import Document, EnrichedChunk, SecurityContext
from .base import DocumentLoader

_FENCE = "---"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.lstrip().startswith(_FENCE):
        return {}, text
    parts = text.lstrip().split(_FENCE, 2)
    if len(parts) < 3:
        return {}, text
    meta = yaml.safe_load(parts[1]) or {}
    return meta, parts[2].strip()


class MarkdownLoader(DocumentLoader):
    """Load every ``*.md`` file in a directory as a governed Document."""

    def __init__(self, corpus_dir: str | Path) -> None:
        self.corpus_dir = Path(corpus_dir)

    def load(self) -> list[Document]:
        docs: list[Document] = []
        for path in sorted(self.corpus_dir.glob("*.md")):
            meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
            if "allowed_roles" not in meta and "clearance_level" not in meta:
                raise ValueError(
                    f"{path.name}: missing security frontmatter "
                    "(allowed_roles / clearance_level). Refusing to ingest "
                    "un-governed content."
                )
            security = SecurityContext(
                allowed_roles=meta.get("allowed_roles", []) or ["PUBLIC"],
                clearance_level=int(meta.get("clearance_level", 0)),
                owner_department=meta.get("owner_department", "UNASSIGNED"),
            )
            docs.append(
                Document(
                    doc_id=meta.get("doc_id", path.stem),
                    title=meta.get("title", path.stem.replace("_", " ").title()),
                    content=body,
                    summary=meta.get("summary", ""),
                    security=security,
                    source_uri=str(path),
                )
            )
        return docs


def chunk_document(doc: Document, config: EngineConfig | None = None) -> list[EnrichedChunk]:
    """Split a document into windows that inherit its ACLs.

    Paragraph boundaries are respected first, then an oversized paragraph is
    hard-split with overlap so we never lose context mid-table.
    """
    cfg = config or EngineConfig()
    paragraphs = [p.strip() for p in doc.content.split("\n\n") if p.strip()]
    windows: list[str] = []
    buf = ""
    for para in paragraphs:
        if buf and len(buf) + len(para) + 2 > cfg.chunk_size:
            windows.append(buf)
            buf = ""
        if len(para) > cfg.chunk_size:
            if buf:
                windows.append(buf)
                buf = ""
            start = 0
            while start < len(para):
                windows.append(para[start : start + cfg.chunk_size])
                start += max(1, cfg.chunk_size - cfg.chunk_overlap)
        else:
            buf = f"{buf}\n\n{para}".strip() if buf else para
    if buf:
        windows.append(buf)

    return [
        EnrichedChunk(
            chunk_id=f"{doc.doc_id}::chunk-{i:03d}",
            parent_doc_id=doc.doc_id,
            parent_title=doc.title,
            content=text,
            security=doc.security,  # <-- ACL inheritance happens here
            ordinal=i,
        )
        for i, text in enumerate(windows)
    ]

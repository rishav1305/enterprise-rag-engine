"""Core data contracts for the Adaptive Enterprise RAG engine.

Every object that crosses a layer boundary is a Pydantic model. Security
metadata is *not* optional bookkeeping bolted on at query time — it is a
required field on the chunk itself, validated at the point of ingestion.
That single design decision is what makes permission-aware governance
enforceable rather than aspirational.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RAGArchitecture(str, Enum):
    """Which retrieval strategy the router selected for a query."""

    ADVANCED_HYBRID = "advanced_hybrid"   # single-hop factual lookup
    GRAPH_RAG = "graph_rag"               # relationship / cross-entity questions
    AGENTIC_LOOP = "agentic_loop"         # multi-step, multi-hop reasoning


class SecurityContext(BaseModel):
    """Role-based access control footprint captured at ingestion time.

    A chunk inherits the clearance of the source it came from. The governance
    layer compares this against the active session before any chunk is allowed
    into the generation context window.
    """

    model_config = ConfigDict(frozen=True)

    allowed_roles: list[str] = Field(
        default_factory=list,
        description='Roles permitted to read this content, e.g. ["HR_ADMIN", "C_SUITE"].',
    )
    clearance_level: int = Field(
        0, ge=0, le=5, description="0 = public, 5 = board-only."
    )
    owner_department: str = Field("UNASSIGNED", description="Originating department.")
    sensitivity_class: str = Field(
        "", description="A-N sensitivity class from the Meridian access model."
    )
    need_to_know_roles: list[str] = Field(
        default_factory=list,
        description="Roles satisfying need-to-know; empty = level+allowed_roles only.",
    )

    @field_validator("allowed_roles", "need_to_know_roles")
    @classmethod
    def _normalise_roles(cls, roles: list[str]) -> list[str]:
        # Upper-case and de-duplicate while preserving order — roles are
        # case-insensitive identifiers, and silent dupes hide policy bugs.
        seen: set[str] = set()
        out: list[str] = []
        for r in roles:
            key = r.strip().upper()
            if key and key not in seen:
                seen.add(key)
                out.append(key)
        return out

    @property
    def is_public(self) -> bool:
        return self.clearance_level == 0 and (
            not self.allowed_roles or "PUBLIC" in self.allowed_roles
        )


class Document(BaseModel):
    """A source document with its global summary and security footprint."""

    doc_id: str
    title: str
    content: str
    security: SecurityContext
    summary: str = ""
    source_uri: str = ""
    # G0: governance metadata that chunks inherit — e.g. {"partial_for": [roles]} for
    # the row-scoped (partial) access leg of access.evaluate.
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


class EnrichedChunk(BaseModel):
    """A retrievable unit: raw text + a contextual anchor + inherited ACLs."""

    model_config = ConfigDict(validate_assignment=True)

    chunk_id: str
    parent_doc_id: str
    parent_title: str
    content: str
    contextual_anchor: str = Field(
        "",
        description="1-sentence anchor prepended via Contextual Retrieval (Layer 2).",
    )
    security: SecurityContext
    ordinal: int = 0
    # P0.10: modality tag. "text" (default — back-compat with all text-only call
    # sites) | "image" | "table" | "ocr" | "figure". Non-text chunks carry their
    # binary/structured payload in metadata under MULTIMODAL_PAYLOAD_KEY so
    # governance (redact_chunk) has one place to withhold it.
    modality: str = "text"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def embedding_text(self) -> str:
        """Text that is actually indexed/embedded — anchor + content."""
        anchor = self.contextual_anchor.strip()
        return f"{anchor}\n{self.content}".strip() if anchor else self.content

    @property
    def doc_hash(self) -> str:
        """Immutable content hash used in the citation chain."""
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()[:16]


class Session(BaseModel):
    """The active caller. The governance layer's source of truth for identity."""

    user_id: str
    roles: list[str] = Field(default_factory=list)
    clearance_level: int = Field(0, ge=0, le=5)

    @field_validator("roles")
    @classmethod
    def _upper(cls, roles: list[str]) -> list[str]:
        # Reject control chars in role names: the cache scope fingerprint joins
        # roles with \x1f, so a role literally containing a control char could
        # alias two distinct scopes. Roles are plain identifiers — refuse to start
        # on a malformed one (fail-closed, defense in depth).
        out: list[str] = []
        for r in roles:
            r = r.strip()
            if not r:
                continue
            if any(ord(ch) < 0x20 for ch in r):
                raise ValueError(f"role contains a control character: {r!r}")
            out.append(r.upper())
        return out


class ScoredChunk(BaseModel):
    """A chunk paired with its fused retrieval score."""

    chunk: EnrichedChunk
    score: float
    lexical_rank: int | None = None
    dense_rank: int | None = None


class Citation(BaseModel):
    """A verified source reference with an immutable content hash."""

    chunk_id: str
    parent_doc_id: str
    parent_title: str
    doc_hash: str
    quote: str


class GovernanceDecision(BaseModel):
    """Per-chunk record of why a chunk was kept or dropped — the audit trail."""

    chunk_id: str
    parent_doc_id: str
    decision: str  # "allow" | "mask" | "partial" | "deny"
    reason: str
    required_roles: list[str] = Field(default_factory=list)
    session_roles: list[str] = Field(default_factory=list)
    mask_reason: str = ""  # "pii_mask" | "field_acl_mask" when decision == "mask"
    scope: str = ""        # partial-access scope predicate when decision == "partial"


class RAGResponse(BaseModel):
    """The final, structured output. Always carries its governance trail."""

    query: str
    answer: str
    architecture: RAGArchitecture
    citations: list[Citation] = Field(default_factory=list)
    access_denied: bool = False
    retrieved: int = 0
    admitted: int = 0
    blocked: int = 0
    # the GOVERNED withheld count (deny+mask+partial). Carried explicitly so a CACHE
    # HIT (which intentionally returns an empty trail) still reports the true count —
    # the client n_withheld is stable warm vs cold.
    n_withheld: int = 0
    governance_trail: list[GovernanceDecision] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

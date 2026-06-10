"""P0.10 T0 — EnrichedChunk.modality + payload helpers (the multimodal seam).

A non-text chunk tags its modality and carries its binary/structured payload in
metadata under ONE conventional key, so redaction has a single place to withhold it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.multimodal.payload import (  # noqa: E402
    MULTIMODAL_PAYLOAD_KEY,
    attach_payload,
    get_payload,
    strip_payload,
)
from rag_engine.schemas import EnrichedChunk, SecurityContext  # noqa: E402


def _chunk(modality="text", metadata=None):
    return EnrichedChunk(
        chunk_id="c", parent_doc_id="d", parent_title="t", content="caption",
        modality=modality, metadata=metadata or {},
        security=SecurityContext(allowed_roles=[], clearance_level=0,
                                 sensitivity_class="A", need_to_know_roles=[]),
    )


def test_modality_defaults_to_text_backcompat():
    # an EnrichedChunk built without modality is "text" (back-compat with all
    # existing text-only call sites).
    c = EnrichedChunk(chunk_id="c", parent_doc_id="d", parent_title="t",
                      content="x",
                      security=SecurityContext(allowed_roles=[], clearance_level=0,
                                               sensitivity_class="A",
                                               need_to_know_roles=[]))
    assert c.modality == "text"


def test_modality_can_be_set():
    assert _chunk(modality="image").modality == "image"


def test_attach_and_get_payload():
    md = {}
    attach_payload(md, b"\x89PNG fake image bytes")
    assert md[MULTIMODAL_PAYLOAD_KEY] == b"\x89PNG fake image bytes"
    assert get_payload(md) == b"\x89PNG fake image bytes"


def test_get_payload_none_when_absent():
    assert get_payload({}) is None
    assert get_payload({"other": 1}) is None


def test_strip_payload_removes_it():
    md = {"other": "kept"}
    attach_payload(md, b"table bytes")
    strip_payload(md)
    assert get_payload(md) is None       # payload gone
    assert md["other"] == "kept"          # unrelated metadata preserved


def test_strip_payload_idempotent():
    md = {}
    strip_payload(md)   # no payload -> no error
    assert get_payload(md) is None

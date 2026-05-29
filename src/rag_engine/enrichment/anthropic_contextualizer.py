"""Production contextualizer using Anthropic's Contextual Retrieval pattern.

The full document is sent once as a *cached* prefix (prompt caching), then each
chunk is situated against it. This is the technique from Anthropic's
"Contextual Retrieval" writeup, which reported large reductions in
failed-retrieval rate when combined with hybrid search + reranking.

Activated only when ``ANTHROPIC_API_KEY`` is set; otherwise the engine falls
back to the local heuristic so nothing breaks offline.
"""

from __future__ import annotations

import os

from ..config import EngineConfig
from ..schemas import Document, EnrichedChunk
from .base import Contextualizer

_PROMPT = (
    "Here is a chunk we want to situate within the whole document.\n"
    "<chunk>\n{chunk}\n</chunk>\n\n"
    "Give a short, standalone sentence (max 30 words) that situates this chunk "
    "within the document for the purposes of improving search retrieval. "
    "Answer ONLY with that sentence."
)


class AnthropicContextualizer(Contextualizer):
    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        try:
            import anthropic  # noqa: F401
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "anthropic SDK not installed. `pip install anthropic` or set "
                "RAG_CONTEXTUALIZER=local."
            ) from exc

    def annotate(self, doc: Document, chunks: list[EnrichedChunk]) -> list[EnrichedChunk]:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        for c in chunks:
            msg = client.messages.create(
                model=self.config.anthropic_model,
                max_tokens=128,
                system=[
                    {
                        "type": "text",
                        "text": f"<document>\n{doc.content}\n</document>",
                        # cache the whole-document prefix across all chunks
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": _PROMPT.format(chunk=c.content)}],
            )
            c.contextual_anchor = msg.content[0].text.strip()
        return chunks

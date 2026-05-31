"""Production generator using Claude, constrained to the admitted context.

The system prompt hard-binds the model to the supplied context and instructs it
to refuse rather than speculate. Because governance has already stripped any
unauthorised chunk, the model is never even shown restricted text.
"""

from __future__ import annotations

import os

from ..config import EngineConfig
from ..schemas import ScoredChunk

_SYSTEM = (
    "You are an enterprise assistant. Answer ONLY using the provided context. "
    "If the context does not contain the answer, say you do not have authorised "
    "information on that topic. Never use outside knowledge. Cite source titles."
)


class AnthropicGenerator:
    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        try:
            import anthropic  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "anthropic SDK not installed. `pip install anthropic` or use the "
                "extractive generator (RAG_GENERATOR=extractive)."
            ) from exc

    def generate(self, query: str, admitted: list[ScoredChunk]) -> str:
        if not admitted:
            return "Access Denied due to security clearances."
        import anthropic

        context = "\n\n".join(
            f"[{sc.chunk.parent_title}] {sc.chunk.embedding_text}" for sc in admitted
        )
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=512,
            system=_SYSTEM,
            messages=[
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
            ],
        )
        return msg.content[0].text.strip()

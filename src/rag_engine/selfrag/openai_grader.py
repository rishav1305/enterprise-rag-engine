"""OpenAICompatGrader — LLM-backed self-RAG grader (Groq/NVIDIA, creds-gated).

Mirrors generation/openai_compat.py: an OpenAI-compatible chat client drafts a
structured JSON grade. The deterministic FakeGrader is always used in CI; this is
the live path, gated on @pytest.mark.llm + an API key. The client call is isolated
in ``_complete`` so the prompt-building + JSON parsing are unit-testable with a stub
(no network), and only the actual network call is creds-gated.

The grade JSON contract is fixed + parsed defensively (a malformed LLM response
fail-closes to NOT sufficient / NOT grounded — you never pass on an unparseable
grade).
"""

from __future__ import annotations

import json

from ..schemas import ScoredChunk
from .grader import GroundednessGrade, RelevanceGrade

_RELEVANCE_SYS = (
    "You grade whether the retrieved CONTEXT is sufficient to answer the QUESTION. "
    "Reply with ONLY a JSON object: "
    '{"sufficient": true|false, "score": 0.0-1.0, "reason": "..."}.'
)
_GROUNDED_SYS = (
    "You grade whether the ANSWER is fully supported by the CONTEXT (no hallucination). "
    "Reply with ONLY a JSON object: "
    '{"grounded": true|false, "score": 0.0-1.0, "reason": "...", '
    '"unsupported_spans": ["..."]}.'
)


def _context_text(chunks: list[ScoredChunk]) -> str:
    return "\n\n".join(f"[{c.chunk.chunk_id}] {c.chunk.content}" for c in chunks)


class OpenAICompatGrader:
    def __init__(self, base_url: str, model: str, api_key: str) -> None:
        self.base_url = base_url
        self.model = model
        self.api_key = api_key

    def _complete(self, system: str, user: str) -> str:  # pragma: no cover - live path
        from openai import OpenAI

        client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0,
        )
        return resp.choices[0].message.content.strip()

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Defensive parse — strip code fences, fail-closed on garbage."""
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):]
        try:
            start, end = text.find("{"), text.rfind("}")
            return json.loads(text[start:end + 1]) if start >= 0 else {}
        except (ValueError, json.JSONDecodeError):
            return {}

    def grade_relevance(self, query: str, chunks: list[ScoredChunk]) -> RelevanceGrade:
        if not chunks:
            return RelevanceGrade(False, 0.0, "no chunks retrieved")
        user = f"QUESTION:\n{query}\n\nCONTEXT:\n{_context_text(chunks)}"
        data = self._parse_json(self._complete(_RELEVANCE_SYS, user))
        # fail-closed + STRICT: sufficient ONLY on a real JSON `true`. Untrusted LLM
        # output like {"sufficient": "yes maybe"} or "true" (string) must NOT pass via
        # truthy coercion — require the boolean True.
        return RelevanceGrade(
            sufficient=(data.get("sufficient") is True),
            score=float(data.get("score", 0.0) or 0.0),
            reason=str(data.get("reason", "")),
        )

    def grade_groundedness(
        self, query: str, answer: str, chunks: list[ScoredChunk]
    ) -> GroundednessGrade:
        if not chunks:
            return GroundednessGrade(False, 0.0, "no context to ground on")
        user = (f"QUESTION:\n{query}\n\nANSWER:\n{answer}\n\n"
                f"CONTEXT:\n{_context_text(chunks)}")
        data = self._parse_json(self._complete(_GROUNDED_SYS, user))
        return GroundednessGrade(
            # STRICT: grounded ONLY on a real JSON `true` (no truthy coercion of
            # untrusted LLM strings) — fail-closed otherwise.
            grounded=(data.get("grounded") is True),
            score=float(data.get("score", 0.0) or 0.0),
            reason=str(data.get("reason", "")),
            unsupported_spans=list(data.get("unsupported_spans", []) or []),
        )


__all__ = ["OpenAICompatGrader"]

"""Generation seam. The generator only ever sees governance-approved chunks."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import ScoredChunk


class Generator(ABC):
    @abstractmethod
    def generate(self, query: str, admitted: list[ScoredChunk]) -> str:
        """Produce an answer grounded strictly in ``admitted`` chunks."""
        raise NotImplementedError

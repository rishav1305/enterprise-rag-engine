"""Layer 3 — Adaptive routing seam."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import RAGArchitecture


class QueryRouter(ABC):
    @abstractmethod
    def route(self, query: str) -> RAGArchitecture:
        raise NotImplementedError

"""Self-RAG: corrective grading + a governance-preserving agentic loop (P0.8).

The headline invariant: the corrective loop NEVER becomes a permission-escalation
path. The loop reformulates QUERY TEXT only and threads the fixed session into the
injected session-scoped retrieve_fn, so every iteration only ever sees authorized
content (it never constructs an allowlist itself).
"""

from .grader import (
    FakeGrader,
    Grader,
    GroundednessGrade,
    RelevanceGrade,
)
from .loop import CorrectiveLoop, LoopResult, LoopStep
from .openai_grader import OpenAICompatGrader

__all__ = [
    "Grader", "FakeGrader", "OpenAICompatGrader",
    "RelevanceGrade", "GroundednessGrade",
    "CorrectiveLoop", "LoopResult", "LoopStep",
]

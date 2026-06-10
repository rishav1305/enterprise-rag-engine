"""Text-to-SQL agent — NL -> guarded read-only SQL -> MASKED result rows -> answer.

The result rows pass through ``result_masking.mask_rows`` BEFORE they become model
context — the 🔴 hard gate that makes text-to-SQL non-leaking.
"""

from .agent import SqlAnswer, TextToSqlAgent
from .result_masking import mask_rows

__all__ = ["TextToSqlAgent", "SqlAnswer", "mask_rows"]

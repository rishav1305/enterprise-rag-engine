"""Permission-aware semantic cache (P0.7).

The headline governance invariant: a cached answer must NEVER be served across a
permission boundary. The cache key incorporates the session's authorization scope
(AuthScope), AND the cache re-applies governance on every hit (defense in depth).
"""

from .key import AuthScope
from .observability import record_cache_hit
from .semantic_cache import CachedResult, SemanticCache

__all__ = ["AuthScope", "SemanticCache", "CachedResult", "record_cache_hit"]

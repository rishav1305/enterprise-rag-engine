"""CDC / streaming re-embedding + governance propagation (P0.9).

The headline invariant: a data change must NEVER leave stale authorization
reachable. CdcProcessor applies change events to the store AND evicts affected
cache entries, so delete/reclassify propagate to retrieval, the allowlist, and the
semantic cache fail-closed. Re-embedding preserves SecurityContext.
"""

from .events import ChangeOp, ChunkChangeEvent
from .processor import CdcProcessor

__all__ = ["ChangeOp", "ChunkChangeEvent", "CdcProcessor"]

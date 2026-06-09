"""TurboVecIndex — the compressed vector ANN index (P0.2b).

Wraps ``turbovec.IdMapIndex`` (TurboQuant, bit_width=4, S1-validated: cold-loads
in <1s, fits serverless RAM, allowlist filtered-search is a free permission
PRE-filter). External uint64 keys come from an ``IdMap`` that bijects to SurrealDB
chunk record-ids; the map is persisted next to the ``.tvim`` so a reloaded index
resolves ids exactly.

TurboVec owns the ANN; SurrealDB holds vectors-by-id + metadata (per spike S2).
``search(allowlist_chunk_ids=...)`` enforces permissions at the index — a chunk
whose id is not in the allowlist is never even a candidate (drop-before-search).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .id_map import IdMap

_BIT_WIDTH = 4  # S1: best recall, ~516 B/vec, still serverless-loadable


@dataclass(frozen=True, slots=True)
class VectorHit:
    chunk_id: str
    score: float


class TurboVecIndex:
    def __init__(self, dim: int, bit_width: int = _BIT_WIDTH) -> None:
        import turbovec

        self.dim = dim
        self.bit_width = bit_width
        self._index = turbovec.IdMapIndex(dim=dim, bit_width=bit_width)
        self._id_map = IdMap()
        self._prepared = False

    # ---- build ---------------------------------------------------------
    def add(self, chunk_ids: list[str], vectors: np.ndarray) -> None:
        if len(chunk_ids) != vectors.shape[0]:
            raise ValueError("chunk_ids and vectors length mismatch")
        u64 = np.array([self._id_map.to_u64(c) for c in chunk_ids], dtype=np.uint64)
        self._index.add_with_ids(np.ascontiguousarray(vectors, dtype=np.float32), u64)
        self._prepared = False

    # ---- query ---------------------------------------------------------
    def search(
        self,
        query: np.ndarray,
        k: int,
        allowlist_chunk_ids: list[str] | None = None,
    ) -> list[VectorHit]:
        if not self._prepared:
            self._index.prepare()
            self._prepared = True
        q = np.ascontiguousarray(query, dtype=np.float32).reshape(1, -1)
        kwargs = {}
        if allowlist_chunk_ids is not None:
            allow = [self._id_map.to_u64(c) for c in allowlist_chunk_ids
                     if c in self._id_map._fwd]  # only ids actually in the index
            if not allow:
                return []  # nothing the session may see -> empty (fail-closed)
            kwargs["allowlist"] = np.array(allow, dtype=np.uint64)
        scores, ids = self._index.search(q, min(k, len(self._id_map)), **kwargs)
        out: list[VectorHit] = []
        for score, u in zip(scores[0].tolist(), ids[0].tolist()):
            cid = self._id_map.to_chunk_id(int(u))
            if cid is not None:
                out.append(VectorHit(chunk_id=cid, score=float(score)))
        return out

    def __len__(self) -> int:
        return len(self._id_map)

    # ---- persistence ---------------------------------------------------
    def write(self, path: str) -> None:
        self._index.write(path)
        Path(path + ".idmap.json").write_text(json.dumps(self._id_map.to_dict()))

    @classmethod
    def load(cls, path: str, dim: int | None = None, bit_width: int = _BIT_WIDTH) -> "TurboVecIndex":
        import turbovec

        idx_obj = turbovec.IdMapIndex.load(path)
        inst = cls.__new__(cls)
        inst._index = idx_obj
        inst.dim = idx_obj.dim if dim is None else dim
        inst.bit_width = bit_width
        inst._id_map = IdMap.from_dict(json.loads(Path(path + ".idmap.json").read_text()))
        inst._prepared = False
        return inst

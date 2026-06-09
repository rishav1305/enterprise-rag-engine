"""Offline TurboVec build (the §3.4 build-pipeline seam).

Build-time batch (off the request path): take the vector-mode chunks from the
Meridian estate, embed them deterministically (HashingEmbedder for CI; the Voyage
adapter is the swappable production path), build the TurboVec index, write
``index.tvim`` (+ ``.idmap.json``), and upsert the vectors-by-id into SurrealDB
``chunk`` rows (per S2: SurrealDB holds vectors-by-id, TurboVec serves the ANN).

Each chunk carries its governing asset_id + sensitivity class/level so the
allowlist pre-filter and downstream masking have what they need.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from rag_engine.retrieval.embedders import HashingEmbedder  # noqa: E402
from rag_engine.retrieval.turbovec_index import TurboVecIndex  # noqa: E402
from seeds.emit import build_estate  # noqa: E402

# assets whose retrieval_mode is vector are the embeddable corpus.
_VECTOR_MODE = "vector"


def _chunk_texts(scale: float):
    """Yield (chunk_id, text, asset_id, cls, level) for vector-mode estate rows."""
    manifest, outputs = build_estate(scale=scale)
    by_id = {a.asset_id: a for a in manifest.assets}
    for asset_id, out in outputs.items():
        asset = by_id.get(asset_id)
        if asset is None or asset.retrieval_mode != _VECTOR_MODE:
            continue
        for i, row in enumerate(out.rows):
            # deterministic chunk text from the row's string-ish fields
            text = " ".join(str(v) for v in row.values() if isinstance(v, str))[:512]
            if not text.strip():
                text = f"{asset_id} record {i}"
            yield (f"{asset_id}-{i:06d}", text, asset_id,
                   asset.sensitivity_class, asset.clearance_level)


def build_index(store, out_path: str, scale: float = 1.0, dim: int = 1024) -> int:
    """Embed vector-mode chunks, build+write the index, upsert vectors to SurrealDB.

    Returns the number of chunks indexed.
    """
    rows = list(_chunk_texts(scale))
    if not rows:
        return 0
    # Align the SurrealDB chunk vector index to the build dim (OVERWRITE-idempotent).
    # The TurboVec index is the ANN; the SurrealDB vec field stores vectors-by-id.
    store.apply_schema(vector_dim=dim)
    emb = HashingEmbedder(dim=dim)
    vectors = emb.embed([r[1] for r in rows]).astype("float32")
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9

    chunk_ids = [r[0] for r in rows]
    idx = TurboVecIndex(dim=dim)
    idx.add(chunk_ids, vectors)
    idx.write(out_path)

    # vectors-by-id + governance footprint into SurrealDB (per S2)
    for (cid, text, asset_id, cls, level), vec in zip(rows, vectors):
        store.upsert_chunk({
            "chunk_id": cid,
            "asset_id": asset_id,
            "cls": cls,
            "level": level,
            "text": text,
            "vec": vec.tolist(),
        })
    return len(rows)

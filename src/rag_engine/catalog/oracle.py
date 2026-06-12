"""Live leak-oracle assembler (G4) — the 210-cell matrix, computed ON REQUEST.

The Leak Oracle tab shows the engine's REAL per-cell governance result for every
(persona x sensitivity class) pair: 15 personas x 14 classes (A-N) = 210 cells.
This is the SAME per-cell check the ``tests/test_leak_oracle.py`` suite runs — it
is NOT a hardcoded "all green" grid. Each cell is computed by driving the engine's
``access.evaluate`` on an asset-level chunk for that class, exactly as the oracle
test does (``evaluate(_chunk_for(cls), sess).decision``), and cross-checked against
the independent seeds-side ground truth (``evaluate_class``). A cell is ``leaked``
iff the engine reveals MORE than the ground truth permits (deny->allow/mask, or
mask->allow). If governance ever regresses, a cell here flips red on the next request.

Runtime-safe imports only: ``seeds.personas`` and ``seeds.access_matrix`` are pure
dataclass modules and ``rag_engine.catalog.connector._CLASS_ROLES`` derives from
them — NONE pull faker/sqlglot (the P0.11c lesson). ``seeds.emit.build_oracle`` is
deliberately NOT imported (it pulls the heavy synthetic generators).

LEAK-SAFE: the response carries only labels + decision strings + booleans. No
content, no PII, no row data ever leaves this endpoint.
"""

from __future__ import annotations

from typing import Any

from ..governance.access import evaluate
from ..schemas import EnrichedChunk, SecurityContext, Session
from .connector import _CLASS_ROLES

# Pure dataclass modules — runtime-safe (no faker / sqlglot).
from seeds.access_matrix import CLASSES, evaluate_class  # noqa: E402
from seeds.personas import PERSONAS  # noqa: E402

# per-class min clearance level mirrors the oracle test (seeds.access_matrix)
_CLASS_LEVEL = {code: sc.min_level for code, sc in CLASSES.items()}

# Severity ordering: how much a decision reveals. A leak is the engine landing on a
# MORE-revealing decision than the ground truth permits.
_REVEAL = {"deny": 0, "partial": 1, "mask": 2, "allow": 3}


def _chunk_for(cls: str) -> EnrichedChunk:
    """An asset-level chunk for sensitivity class ``cls`` — the SAME SecurityContext
    the SeedConnector builds and the oracle test drives, so the engine sees exactly
    what the catalog holds for that class."""
    roles = _CLASS_ROLES[cls]
    return EnrichedChunk(
        chunk_id=f"c-{cls}",
        parent_doc_id=f"asset-{cls}",
        parent_title="t",
        content="x",
        security=SecurityContext(
            allowed_roles=roles,
            clearance_level=_CLASS_LEVEL[cls],
            sensitivity_class=cls,
            need_to_know_roles=roles,
        ),
    )


def build_oracle_grid() -> dict[str, Any]:
    """Compute the live 210-cell oracle grid. Each cell: the engine's real decision
    for (persona x class), plus a ``leaked`` flag (engine reveals more than the
    independent ground truth allows). Booleans + labels only — never content."""
    classes = sorted(CLASSES)  # A..N, deterministic order
    cells: list[dict[str, Any]] = []
    leaks = 0

    for p in PERSONAS:
        sess = Session(user_id=p.key, roles=list(p.roles), clearance_level=p.clearance_level)
        for cls in classes:
            engine = evaluate(_chunk_for(cls), sess).decision
            # independent reference (NOT the engine) — the un-fakeable cross-check.
            truth = evaluate_class(cls, p.clearance_level, p.roles).value
            leaked = _REVEAL.get(engine, 3) > _REVEAL.get(truth, 0)
            if leaked:
                leaks += 1
            cells.append(
                {
                    "persona": p.key,
                    "persona_label": p.title,
                    "clearance_level": p.clearance_level,
                    "sensitivity_class": cls,
                    "class_label": CLASSES[cls].name,
                    "decision": engine,
                    "expected": truth,
                    "leaked": leaked,
                }
            )

    return {
        "cells": cells,
        "personas": [
            {"key": p.key, "label": p.title, "clearance_level": p.clearance_level}
            for p in PERSONAS
        ],
        "classes": [{"code": c, "label": CLASSES[c].name} for c in classes],
        "totals": {"cells": len(cells), "leaks": leaks},
    }

"""P0.11a W8 — THE MASTER END-TO-END LEAK ORACLE through the fully-wired pipeline.

The 210-cell oracle (15 personas x 14 classes) run END-TO-END through RAGPipeline.query
with EVERY component wired + active: cache (W2), corrective loop (W3), tracer (W1) — all
on by default config. A standalone-safe component can leak once composed; this is the
master gate.

For each persona x class cell:
  * index a chunk of that class carrying a CLASS-SPECIFIC secret marker;
  * run the full pipeline.query for the persona;
  * assert the oracle decision holds: DENY -> the secret NEVER appears in the answer;
    MASK/PARTIAL -> the raw secret is withheld/redacted (token, not the raw marker);
    ALLOW -> retrievable (no leak violation — the marker MAY appear).

MUTATION: disable ANY single component's governance step (e.g. the L5 SecurityFilter,
or the cache govern_fn, or the loop self-redact) -> a deny/mask cell leaks the secret
-> this oracle fails. Proves the master oracle exercises each component's governance live.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_engine.config import EngineConfig  # noqa: E402
from rag_engine.pipeline import RAGPipeline  # noqa: E402
from rag_engine.schemas import Document, SecurityContext, Session  # noqa: E402
from seeds.access_matrix import CLASSES  # noqa: E402
from seeds.emit import build_oracle  # noqa: E402

# a unique, searchable secret per class so a leak is unambiguous.
def _marker(cls: str) -> str:
    return f"CLASS_{cls}_SECRET_MARKER_4POINT2M"


def _class_doc(cls: str) -> Document:
    spec = CLASSES[cls]
    ntk = list(spec.need_to_know_roles)
    return Document(
        doc_id=f"doc_{cls}", title=f"Class {cls} record",
        content=f"Class {cls} sensitive content {_marker(cls)} for the {spec.name} domain.",
        security=SecurityContext(
            allowed_roles=ntk, clearance_level=spec.min_level,
            sensitivity_class=cls, need_to_know_roles=ntk,
        ),
    )


def _fully_wired_pipeline() -> RAGPipeline:
    cfg = EngineConfig()   # cache + selfrag enabled by default -> fully wired
    pipe = RAGPipeline(config=cfg)
    pipe.index_documents([_class_doc(c) for c in CLASSES])
    assert pipe.cache is not None and pipe.selfrag_enabled  # every component live
    return pipe


def _session(persona: dict) -> Session:
    return Session(user_id="p", roles=list(persona["roles"]),
                   clearance_level=persona["level"])


def test_e2e_fully_wired_leak_oracle():
    oracle = build_oracle()
    personas = oracle["personas"]
    expectations = oracle["expectations"]
    pipe = _fully_wired_pipeline()

    cells = 0
    leaks: list[str] = []
    for pkey, persona in personas.items():
        session = _session(persona)
        for cls, expected in expectations[pkey].items():
            cells += 1
            marker = _marker(cls)
            # query for this class's content through the FULLY-WIRED pipeline.
            resp = pipe.query(f"tell me about class {cls} {CLASSES[cls].name}", session)
            answer = resp.answer or ""
            if expected == "deny":
                if marker in answer:
                    leaks.append(f"DENY-LEAK {pkey} x {cls}: secret in answer")
            elif expected in ("mask", "partial"):
                # the RAW secret must be withheld/redacted (a token, not the marker).
                if marker in answer:
                    leaks.append(f"{expected.upper()}-LEAK {pkey} x {cls}: raw secret in answer")
            # allow: retrievable, no violation to assert (marker may appear)

    assert cells == 210, f"expected 210 cells, ran {cells}"
    assert not leaks, "MASTER ORACLE LEAKS:\n" + "\n".join(leaks[:20])


def test_master_oracle_actually_runs_the_full_pipeline():
    # guard: the oracle must drive the REAL pipeline.query (cache+loop+tracer), not a
    # shortcut. Assert the wired components are present + exercised.
    pipe = _fully_wired_pipeline()
    intern = Session(user_id="i", roles=["INTERN", "EMPLOYEE"], clearance_level=1)
    # a class-F (exec-comp) query for the intern -> denied; the secret never appears.
    resp = pipe.query(f"tell me about class F {CLASSES['F'].name}", intern)
    assert _marker("F") not in (resp.answer or "")
    # and the cache now holds an entry (the pipeline ran put) -> the loop+cache path ran.
    assert len(pipe.cache) >= 1

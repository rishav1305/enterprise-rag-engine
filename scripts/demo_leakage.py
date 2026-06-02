#!/usr/bin/env python3
"""Run the adversarial data-leakage scenario and print the governance trail.

    python scripts/demo_leakage.py

Shows the same query hitting the same index under two identities — a low-level
INTERN and a privileged CFO — and prints exactly which chunks were admitted,
which were blocked and why, plus the RAGAS-style eval gate result.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_engine import RAGPipeline, Session  # noqa: E402
from rag_engine.evaluation.gate import evaluate_gate  # noqa: E402
from rag_engine.evaluation.metrics import (  # noqa: E402
    context_recall,
    governance_leak_rate,
)

QUERY = (
    "What are our upcoming financial projections and current executive "
    "salary structures?"
)
RESTRICTED = {"fin-q3-2026", "hr-exec-comp-2026"}

BOLD, DIM, RED, GRN, YEL, RST = "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[0m"


def banner(text: str) -> None:
    print(f"\n{BOLD}{'=' * 72}\n{text}\n{'=' * 72}{RST}")


def run(pipe: RAGPipeline, session: Session) -> None:
    banner(f"SESSION  user={session.user_id}  roles={session.roles}  L{session.clearance_level}")
    resp = pipe.query(QUERY, session)
    print(f"{DIM}query:{RST} {QUERY}")
    print(f"{DIM}router selected:{RST} {resp.architecture.value}")
    print(f"{DIM}retrieved={resp.retrieved}  admitted={resp.admitted}  blocked={resp.blocked}{RST}\n")

    print(f"{BOLD}Governance trail:{RST}")
    for d in resp.governance_trail:
        if d.decision == "allow":
            print(f"  {GRN}✓ ALLOW{RST}  {d.parent_doc_id:<18} {DIM}{d.reason}{RST}")
        else:
            print(f"  {RED}✗ DROP {RST}  {d.parent_doc_id:<18} {DIM}{d.reason}{RST}")

    print(f"\n{BOLD}Answer:{RST}\n  {resp.answer}")
    if resp.citations:
        print(f"\n{BOLD}Citations (hash-chained):{RST}")
        for c in resp.citations:
            print(f"  • {c.parent_title}  {DIM}[{c.parent_doc_id} #{c.doc_hash}]{RST}")


def main() -> int:
    pipe = RAGPipeline()
    n = pipe.index_corpus(ROOT / "corpus")
    banner(f"Indexed {n} chunks from {ROOT / 'corpus'}")

    intern = Session(user_id="intern-1", roles=["INTERN"], clearance_level=1)
    cfo = Session(user_id="cfo-1", roles=["C_SUITE", "FINANCE"], clearance_level=5)
    run(pipe, intern)
    run(pipe, cfo)

    # ---- eval gate over the INTERN run -------------------------------
    intern_resp = pipe.query(QUERY, intern)
    blocked_docs = {d.parent_doc_id for d in intern_resp.governance_trail if d.decision == "deny"}
    leak = governance_leak_rate(blocked_doc_ids=blocked_docs, forbidden_doc_ids=RESTRICTED)
    retrieved_docs = [h.chunk.parent_doc_id for h in pipe.retriever.retrieve(QUERY)]
    recall = context_recall(retrieved_docs, RESTRICTED)  # did we *find* them
    gate = evaluate_gate(context_recall=recall, context_precision=0.5, leak_rate=leak)

    banner("EVAL GATE")
    color = GRN if gate.passed else RED
    print(f"  retrieval_recall(restricted found) = {gate.context_recall:.2f}")
    print(f"  governance_leak_rate               = {gate.leak_rate:.2f}  {DIM}(0.0 = safe){RST}")
    for m in gate.messages:
        print(f"  {color}• {m}{RST}")
    print(f"\n  {color}{BOLD}GATE {'PASSED' if gate.passed else 'FAILED'}{RST}\n")
    return 0 if gate.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

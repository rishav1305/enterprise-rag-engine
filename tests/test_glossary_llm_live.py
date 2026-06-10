"""P0.4 — live LLM glossary drafter (creds-gated, NOT part of the CI gate).

Marked ``llm`` + skipif no GROQ_API_KEY/NVIDIA_API_KEY. Proves the live drafter
proposes a plausible meaning for an opaque column from its value profile. CI runs
`-m "not cloud and not bq and not llm"`. Read-only; no secrets committed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

_KEY = os.getenv("GROQ_API_KEY") or os.getenv("NVIDIA_API_KEY")


@pytest.mark.llm
@pytest.mark.skipif(not _KEY, reason="no Groq/NVIDIA key")
def test_live_glossary_drafter_proposes_meaning():
    pytest.importorskip("openai")
    from rag_engine.config import EngineConfig
    from rag_engine.enrichment.schema_glossary.drafter import LlmGlossaryDrafter
    from rag_engine.enrichment.schema_glossary.profiler import profile_column

    cfg = EngineConfig()
    drafter = LlmGlossaryDrafter(base_url=cfg.sql_llm_base_url,
                                 model=cfg.sql_llm_model, api_key=_KEY)
    rows = [{"text_5": f"u{i}@example.com"} for i in range(20)]
    prof = profile_column(rows, "tbl_44", "text_5")   # regex_class == "email"
    meaning = drafter.draft("tbl_44", "text_5", prof)
    assert meaning and "email" in meaning.lower()
